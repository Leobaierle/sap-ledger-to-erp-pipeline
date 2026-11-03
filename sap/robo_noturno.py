"""Robô noturno da ACME: SAP → planilha (igual ao processo manual no Excel) → ERP (robô de tela) → conferência pela
ERP API → portal. Roda pelo cron, todo dia às 22:00 (Brasília), a partir de 18/10/2026.

Uso: robo_noturno.py [--ensaio] [--nao-antes AAAA-MM-DDTHH:MM] [--hoje AAAA-MM-DD] [--de AAAA-MM-DD --ate AAAA-MM-DD]
  --ensaio     faz tudo até o "Confirma?" da ERP e responde Não; não grava nada no banco do portal
  --nao-antes  não roda antes desse momento (horário de Brasília) — o cron é diário, a 1ª execução é 18/10/2026 22:00
  --de/--ate   período escolhido no botão "Executar agora" do portal (uma competência, até hoje); a execução fica no
               dia de hoje com esse período

Regras (README.md):
- janela: dia 1 do mês até hoje (roda às 22h); nos primeiros DIAS_MES_ANTERIOR dias do mês também olha o mês anterior,
  para pegar lançamentos de fechamento (cada mês vai no seu lote: mês × 100.000 + n);
- só documentos ainda não importados (contabil.robo_documento); conta SAP sem conta ERP segura o documento
  (pendência no portal); CC sem de-para sai 0;
- numeração: lote = maior lote do mês na ERP + 1; lançamento = maior lançamento do mês + 1;
- importação sem "Sucesso" = "verificar": na noite seguinte o robô confere o lote pela API antes de qualquer coisa e
  nunca repete no escuro;
- documentos só viram "importados" depois da conferência pela API (partidas, lançamentos e D = C iguais à planilha).
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from zoneinfo import ZoneInfo

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path[:0] = [os.path.join(RAIZ, "app"), AQUI]
BRT = ZoneInfo("America/Sao_Paulo")
SIGLA = "EMP"
DIAS_MES_ANTERIOR = 5
SAIDA = os.path.join(AQUI, "saida", "noturno")
PENDENTE = os.path.join(SAIDA, "pendente.json")      # importação sem "Sucesso" esperando conferência
NODE_IMPORTADOR = os.path.join(RAIZ, "rpa", "scripts", "importar_erp.mjs")
BALANCETE_SAP = os.path.join(AQUI, "webgui", "baixar_balancete.sh")


def agora():
    return dt.datetime.now(BRT)


class Execucao:
    """Grava a execução no portal (robo_execucao / robo_etapa / robo_log). Em ensaio só imprime."""
    NOMES = {1: "Extração SAP", 2: "Conversão", 3: "Envio p/ ERP", 4: "Importação ERP"}

    def __init__(self, ensaio, hoje, de, ate):
        self.ensaio, self.id = ensaio, None
        if ensaio:
            return
        import tabelas
        self.tab = tabelas
        with tabelas._conectar() as con, con.transaction():
            con.execute("insert into contabil.robo_config (chave, valor) values ('horario', '\"22:00\"') "
                        "on conflict (chave) do update set valor = excluded.valor, atualizado_em = now()")
            self.id = con.execute("insert into contabil.robo_execucao (data, sigla, status, periodo_de, periodo_ate, "
                                  "iniciado_em) values (%s, %s, 'andamento', %s, %s, now()) returning id",
                                  (hoje, SIGLA, de, ate)).fetchone()[0]
            for n in self.NOMES:
                con.execute("insert into contabil.robo_etapa (execucao_id, n, status) values (%s, %s, 'agendado')",
                            (self.id, n))

    def log(self, etapa, msg, nivel="info"):
        print(f"{agora():%H:%M:%S} [{nivel}] {self.NOMES.get(etapa, etapa)}: {msg}", flush=True)
        if self.id:
            with self.tab._conectar() as con, con.transaction():
                con.execute("insert into contabil.robo_log (execucao_id, nivel, etapa, mensagem) values (%s, %s, %s, %s)",
                            (self.id, nivel, self.NOMES.get(etapa, str(etapa)), msg[:2000]))

    def etapa(self, n, status, nota=None, inicio=False):
        if not self.id:
            return
        with self.tab._conectar() as con, con.transaction():
            if inicio:
                con.execute("update contabil.robo_etapa set status = %s, iniciado_em = now() where execucao_id = %s "
                            "and n = %s", (status, self.id, n))
            else:
                con.execute("update contabil.robo_etapa set status = %s, terminado_em = now(), "
                            "iniciado_em = coalesce(iniciado_em, now()), nota = coalesce(%s, nota) "
                            "where execucao_id = %s and n = %s", (status, nota, self.id, n))

    def arquivo(self, tipo, endereco):
        """Anota o arquivo (razao | planilha) da execução para o download no portal."""
        if self.id:
            with self.tab._conectar() as con, con.transaction():
                con.execute(f"update contabil.robo_execucao set arquivo_{tipo} = %s where id = %s", (endereco, self.id))

    def fim(self, status, **campos):
        print(f"{agora():%H:%M:%S} FIM: {status} {json.dumps(campos, ensure_ascii=False, default=str)[:600]}", flush=True)
        if not self.id:
            return
        cols = ["status = %s", "terminado_em = now()"] + [f"{k} = %s" for k in campos]
        vals = [status] + [json.dumps(v, ensure_ascii=False) if k == "avisos" else v for k, v in campos.items()]
        with self.tab._conectar() as con, con.transaction():
            con.execute(f"update contabil.robo_execucao set {', '.join(cols)} where id = %s", (*vals, self.id))
            con.execute("update contabil.robo_etapa set status = 'naoexec' where execucao_id = %s and status = 'agendado'",
                        (self.id,))
            if status in ("erro", "verificar"):
                con.execute("update contabil.robo_etapa set status = %s, terminado_em = now() where execucao_id = %s "
                            "and status = 'andamento'", (status, self.id))


def garantir_database_url():
    if os.environ.get("DATABASE_URL"):
        return
    raise SystemExit("defina DATABASE_URL (Postgres do portal)")


# ---------- ERP (leitura pela ERP API) ----------

def maior_lote_e_lancamento(ano, mes):
    import erp
    base = mes * 100_000
    lotes = sorted(erp.lotes_existentes(SIGLA, base + 1, base + 99_999, ano))
    if not lotes:
        return base, 0
    st, txt = erp._req("GET", "get-list", {"organization": SIGLA, "entity": "accountingEntry", "fields": "number",
                                            "search": f"fiscalYear EQ {ano} AND accountingLotNumberID EQ {lotes[-1]}",
                                            "size": 1, "page": 0, "sort": "number,desc"})
    if st != 200:
        raise RuntimeError(f"leitura do maior lançamento do lote {lotes[-1]}: HTTP {st} {txt[:200]}")
    c = json.loads(txt).get("content") or []
    return lotes[-1], int(c[0]["number"]) if c else 0


def conferir_lote(ano, lote, esperado):
    import erp
    cab = erp.ler(SIGLA, "accountingLot", f"fiscalYear EQ {ano} AND accountingLotNumber EQ {lote}",
                   "accountingLotNumber", size=5)
    if not cab.get("content"):
        return None
    ps = erp.ler_todas(SIGLA, "accountingEntry", f"fiscalYear EQ {ano} AND accountingLotNumberID EQ {lote}",
                        "number,amount,type")
    lido = {"linhas": len(ps), "lancamentos": len({p["number"] for p in ps}),
            "debito": round(sum(p["amount"] for p in ps if p["type"] == "D"), 2),
            "credito": round(sum(p["amount"] for p in ps if p["type"] == "C"), 2)}
    ok = (lido["linhas"] == esperado["linhas"] and lido["lancamentos"] == esperado["lancamentos"]
          and abs(lido["debito"] - esperado["debito"]) < 0.005 and abs(lido["credito"] - esperado["credito"]) < 0.005)
    return {"confere": ok, **lido}


# ---------- planilhas ----------

def montar_planilhas(pasta_extracao, destino, carimbo, ex):
    """Converte (regras do processo manual), separa por mês e grava CONTABIL_<lote>_<carimbo>.xlsx + .docs.json.
    Devolve (arquivos, resumo) — resumo vai para o robo_banco.pendencias."""
    import conversor
    import lotes
    import tabelas
    from montar_razao import linhas
    from xlsx_rapido import Planilha, gravar

    with tabelas._conectar() as con:
        importados = {d for (d,) in con.execute("select doc from contabil.robo_documento where sigla = %s", (SIGLA,))}
        sem_rateio = {c for (c,) in con.execute("select conta from contabil.robo_conta_sem_rateio where sigla = %s",
                                                 (SIGLA,))}
        antigos = con.execute("select doc, data_lancamento, contas_sap, linhas from contabil.robo_segurado where "
                              "sigla = %s and liberado_em is null", (SIGLA,)).fetchall()
    tab = tabelas.carregar_para_conversao()
    rows = list(linhas(pasta_extracao))
    docs_janela = {conversor._cod(r["Nº doc."]) for r in rows}
    # segurado de fora da janela cuja conta já tem de-para: entra pelas linhas do SAP guardadas no portal
    plano = tab[0]
    for doc, _data, contas, ls in antigos:
        if doc not in docs_janela and doc not in importados and all(c in plano for c in contas) and ls:
            rows += [lotes.linha_de_json(x) for x in ls]
            ex.log(2, f"documento {doc} (segurado antes) liberado: entra nesta execução")
    _g, segurados, resumo = lotes.montar(rows, tab, sem_rateio, importados)
    fora = {conversor._cod(s["doc"]) for s in segurados} | importados
    resumo["segurados"] = segurados
    novos_docs = {conversor._cod(r["Nº doc."]) for r in rows} - fora
    resumo["docs_extraidos"] = len(docs_janela)

    por_mes = defaultdict(list)
    for r in rows:
        if conversor._cod(r["Nº doc."]) not in fora:
            por_mes[(r["Dt.lçto."].year, r["Dt.lçto."].month)].append(r)
    base_data = dt.date(1899, 12, 30)
    larguras = [15, 20, 26, 26, 30, 15, 18, 75, 20, 13, 20, 15]
    estilos = [2, 2, 2, 2, 3, 2, 4, 5, 2, 2, 4, 2]
    arquivos, avisos = [], list(resumo.get("avisos", []))
    for (ano, mes), rs in sorted(por_mes.items()):
        ultimo_lote, ultimo_lanc = maior_lote_e_lancamento(ano, mes)
        razao = list(conversor.razao_de_linhas(rs))
        res = conversor.converter(None, tabelas=tab, linhas_sap=razao, lanc_inicial=ultimo_lanc)
        if res.erros or res.pend_duplicadas or res.pend_contas or res.bloqueado:
            raise RuntimeError(f"conversão {mes:02d}/{ano} com erro: {res.erros[:3]} {res.pend_duplicadas[:3]} "
                               f"{[p['conta'] for p in res.pend_contas][:5]}")
        avisos += [a for a in res.avisos if a not in avisos]
        doc_do_lanc, info, ant, n = {}, {}, object(), ultimo_lanc
        for r in razao:
            if r["doc"] != ant:
                n += 1
                ant = r["doc"]
            d = conversor._cod(r["doc"])
            doc_do_lanc[n] = d
            i = info.setdefault(d, {"ref": conversor._texto_excel(r["ref"]), "textos": []})
            t = conversor._texto_excel(r["texto"])
            if t and t not in i["textos"]:
                i["textos"].append(t)
        de_mes = dt.date(ano, mes, 1)
        ate_mes = max(r["Dt.lçto."] for r in rs)
        for k, (ini, fim) in enumerate(conversor.dividir(res.linhas), 1):
            lote = ultimo_lote + k
            sel = res.linhas[ini:fim]
            nome = f"CONTABIL_{lote}_{carimbo}.xlsx"
            p = Planilha("IMPORTAÇÃO", larguras, estilos)
            p.cabecalho = conversor.CABECALHO_ERP
            p.linhas = ([lote, lanc, part, tipo, (data - base_data).days, conta, valor, hist, doc, cc, vcc, fil]
                        for lanc, part, tipo, data, conta, valor, hist, doc, cc, vcc, fil in sel)
            p.n_linhas = fim - ini
            gravar(os.path.join(destino, nome), [p])
            datas_lanc = {x[0]: x[3] for x in sel}
            docs = [{"doc": doc_do_lanc[l], "data": datas_lanc[l].isoformat(), **info[doc_do_lanc[l]]}
                    for l in sorted(datas_lanc)]
            json.dump(docs, open(os.path.join(destino, nome.replace(".xlsx", ".docs.json")), "w"), ensure_ascii=False)
            arquivos.append({"arquivo": os.path.join(destino, nome), "ano": ano, "lote": lote,
                             "de": de_mes.strftime("%d%m%Y"), "ate": ate_mes.strftime("%d%m%Y"),
                             "linhas": fim - ini, "lancamentos": len(datas_lanc),
                             "debito": round(sum(x[5] for x in sel if x[2] == "D"), 2),
                             "credito": round(sum(x[5] for x in sel if x[2] == "C"), 2)})
    resumo["avisos"] = avisos
    resumo["novos_docs"] = len(novos_docs)
    json.dump(resumo, open(os.path.join(destino, "resumo.json"), "w"), ensure_ascii=False, indent=1, default=str)
    return arquivos, resumo


def guardar(ex, etapa, tipo, caminho, hoje, carimbo):
    """Manda o arquivo para o MinIO e anota na execução (botões de download do portal). Falha aqui só vira aviso:
    não impede a importação. Em ensaio não envia."""
    if not ex.id:
        return
    try:
        import arquivos
        endereco = arquivos.enviar(caminho, f"robo/{hoje:%Y-%m}/{carimbo}/{os.path.basename(caminho)}")
        ex.arquivo(tipo, endereco)
    except Exception as e:                                   # noqa: BLE001
        ex.log(etapa, f"{os.path.basename(caminho)} não foi guardado para download: {e}"[:600], "aviso")


def baixar_balancete_sap(ex, pasta, meses, carimbo):
    """Balancete do próprio SAP (F.01 / RFBILA00, igual ao que a contabilidade exporta à mão em "não convertido"), um
    por mês da janela: sap/webgui/baixar_balancete.sh (VPN + SAP GUI para HTML, só leitura). Falha = aviso, não para o
    robô. Devolve o arquivo (zip se mais de um mês) ou None."""
    feitos = []
    for ano_b, mes_b in meses:
        destino = os.path.join(pasta, "balancete-sap", f"{ano_b}{mes_b:02d}")
        os.makedirs(destino, exist_ok=True)
        try:
            with open(os.path.join(destino, "robo.log"), "w") as log:
                r = subprocess.run([BALANCETE_SAP, f"{ano_b}{mes_b:02d}", destino], stdout=log,
                                   stderr=subprocess.STDOUT, timeout=1200)
            arq = os.path.join(destino, f"BALANCETE_{mes_b:02d}.{ano_b}.xls")
            if r.returncode != 0 or not os.path.exists(arq):
                erro = [l for l in open(os.path.join(destino, "robo.log"), errors="replace") if '"erro"' in l or "Error" in l]
                raise RuntimeError((erro[-1] if erro else f"saída {r.returncode}").strip()[:300])
        except Exception as e:                               # noqa: BLE001
            ex.log(1, f"balancete {mes_b:02d}/{ano_b} do SAP não baixado: {e}"[:600], "aviso")
            continue
        feitos.append(arq)
        ex.log(1, f"balancete {mes_b:02d}/{ano_b} baixado do SAP (F.01/RFBILA00): {os.path.basename(arq)}")
    if len(feitos) <= 1:
        return feitos[0] if feitos else None
    import zipfile
    pacote = os.path.join(pasta, f"BALANCETES_{carimbo}.zip")
    with zipfile.ZipFile(pacote, "w") as z:
        for f in feitos:
            z.write(f, os.path.basename(f))
    return pacote


# ---------- pendência de noites anteriores ----------

def resolver_pendente(ex):
    """Importação anterior sem "Sucesso": confere pela API. Devolve False se ainda não dá para seguir."""
    if not os.path.exists(PENDENTE):
        return True
    import robo_banco
    p = json.load(open(PENDENTE))
    for a in p["arquivos"]:
        if a.get("ok"):
            continue
        c = conferir_lote(a["ano"], a["lote"], a)
        if c is None:
            ex.log(4, f"lote {a['lote']} da execução {p.get('execucao')} NÃO está na ERP: nada foi gravado; os "
                      "documentos voltam a entrar nesta execução")
            a["ok"] = "nao_gravou"
        elif c["confere"]:
            if not ex.ensaio:
                robo_banco.importado(os.path.dirname(a["arquivo"]), a["lote"],
                                     a["arquivo"].replace(".xlsx", ".docs.json"))
            ex.log(4, f"lote {a['lote']} da execução {p.get('execucao')} está na ERP e confere ({c['linhas']} "
                      "partidas): documentos marcados como importados")
            a["ok"] = "gravou"
        else:
            ex.log(4, f"lote {a['lote']} da execução {p.get('execucao')} está na ERP mas NÃO confere com a planilha "
                      f"({c}). Conferir na ERP antes de qualquer nova importação.", "erro")
            return False
    if not ex.ensaio:
        os.replace(PENDENTE, PENDENTE + f".resolvido-{agora():%Y%m%d%H%M}")
    return True


def extrair(ex, pasta, ini, fim_):
    """Extrai BKPF/BSEG/FAGLFLEXA/BSIS + balancete do período por RFC (sap/extrair_razao.py)."""
    origem = os.path.join(AQUI, "saida", f"{ini}-{fim_}")
    r = subprocess.run([sys.executable, os.path.join(AQUI, "extrair_razao.py"), ini, fim_, "--fagl"],
                       capture_output=True, text=True, timeout=3600, env={**os.environ, "SAP_SAIDA": origem})
    saida = (r.stdout + r.stderr).strip()
    if r.returncode != 0 or not os.path.exists(os.path.join(origem, "faglflexa.jsonl")) \
            or not os.path.getsize(os.path.join(origem, "faglflexa.jsonl")):
        raise RuntimeError(f"extração falhou: {saida[-800:]}")
    extracao = os.path.join(pasta, "extracao")
    os.replace(origem, extracao)
    return extracao, saida


def rodar_importador(ex, pedido, arquivos):
    """Roda o importador da ERP e passa cada evento para o log do portal. Devolve (código de saída, eventos)."""
    proc = subprocess.Popen(["node", NODE_IMPORTADOR, pedido], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, cwd=RAIZ)
    eventos = []
    for linha in proc.stdout:
        linha = linha.strip()
        try:
            e = json.loads(linha)
        except ValueError:
            print("  importador:", linha[:300], flush=True)
            continue
        eventos.append(e)
        nivel = "erro" if e["ev"] == "parou" else "aviso" if e["ev"].startswith("AVISO") else "info"
        ex.log(4 if e["ev"] in ("importando", "sucesso", "parou") else 3,
               f"{e['ev']}{': ' + os.path.basename(e['arquivo']) if e.get('arquivo') else ''}"
               f"{' — ' + e['motivo'] if e.get('motivo') else ''}", nivel)
        if e["ev"] == "enviado" and all(any(x["ev"] == "enviado" and x.get("arquivo") == os.path.basename(f["arquivo"])
                                            for x in eventos) for f in arquivos):
            ex.etapa(3, "sucesso", nota="Transferência de arquivos do ERP (Upload) para a pasta AUTOMAÇÃO.")
            ex.etapa(4, "andamento", inicio=True)
    return proc.wait(), eventos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ensaio", action="store_true")
    ap.add_argument("--nao-antes")
    ap.add_argument("--hoje")
    ap.add_argument("--de")
    ap.add_argument("--ate")
    ap.add_argument("--extracao", help="(teste) usa esta extração em vez de extrair do SAP")
    ap.add_argument("--sem-erp", action="store_true", help="(teste) para depois da conversão; exige --ensaio")
    a = ap.parse_args()
    if a.sem_erp and not a.ensaio:
        ap.error("--sem-erp só com --ensaio")
    if bool(a.de) != bool(a.ate) or (a.de and a.hoje):
        ap.error("--de e --ate vão juntos (e sem --hoje)")
    if a.nao_antes and agora() < dt.datetime.fromisoformat(a.nao_antes).replace(tzinfo=BRT):
        print(f"{agora():%Y-%m-%d %H:%M} ainda não: o robô começa em {a.nao_antes} (Brasília)")
        return 0
    os.makedirs(SAIDA, exist_ok=True)
    trava = open(os.path.join(SAIDA, ".trava"), "w")
    try:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("já existe uma execução rodando; saindo")
        return 1
    garantir_database_url()

    hoje = dt.date.fromisoformat(a.hoje) if a.hoje else agora().date()
    de, ate = hoje.replace(day=1), hoje
    if hoje.day <= DIAS_MES_ANTERIOR:
        de = (de - dt.timedelta(days=1)).replace(day=1)
    if a.de:
        de, ate = dt.date.fromisoformat(a.de), dt.date.fromisoformat(a.ate)
        if not (de <= ate <= hoje and (de.year, de.month) == (ate.year, ate.month)):
            ap.error(f"período {de} a {ate}: tem que ser de uma competência só e até hoje")
    carimbo = agora().strftime("%Y%m%d%H%M")
    pasta = os.path.join(SAIDA, carimbo + ("-ensaio" if a.ensaio else ""))
    os.makedirs(pasta, exist_ok=True)
    ex = Execucao(a.ensaio, hoje, de, ate)
    ex.log(1, f"execução {'de ENSAIO ' if a.ensaio else ''}iniciada; janela {de:%d/%m/%Y} a {ate:%d/%m/%Y}")
    try:
        if not resolver_pendente(ex):
            ex.fim("verificar", observacao="Importação de uma noite anterior ficou sem conferência; nada foi feito.")
            return 2

        # 1. extração
        ex.etapa(1, "andamento", inicio=True)
        ini, fim_ = de.strftime("%Y%m%d"), ate.strftime("%Y%m%d")
        if a.extracao:
            ex.log(1, f"(teste) usando a extração {a.extracao}")
            extracao, saida = a.extracao, ""
        else:
            extracao, saida = extrair(ex, pasta, ini, fim_)
        ex.etapa(1, "sucesso", nota=f"Razão de {de:%d/%m/%Y} a {ate:%d/%m/%Y} (BKPF, BSEG, FAGLFLEXA e BSIS)")
        ex.log(1, "extração concluída: " + " | ".join(l.strip() for l in saida.splitlines() if "jsonl" in l)[:600])
        from montar_razao import gravar_xlsx, linhas
        razao = os.path.join(pasta, f"RAZÃO {de:%d.%m.%Y} a {ate:%d.%m.%Y} - extraído {agora():%d.%m.%Y %Hh%M}.xlsx")
        try:
            gravar_xlsx(linhas(extracao), razao)
        except Exception as e:                               # noqa: BLE001
            ex.log(1, f"Razão para download não gerado: {e}"[:600], "aviso")
        else:
            guardar(ex, 1, "razao", razao, hoje, carimbo)
        meses = sorted({(de.year, de.month), (ate.year, ate.month)})
        try:
            import montar_balancete
            for ano_b, mes_b in meses:
                if dif := montar_balancete.conferir(extracao, ano_b, mes_b):
                    ex.log(1, f"balancete {mes_b:02d}/{ano_b}: movimento de {len(dif)} conta(s) diferente do Razão extraído "
                              f"(lançamento feito durante a extração?): "
                              + ", ".join(f"{c} {b:,.2f} x {r:,.2f}" for c, b, r in dif[:5]), "aviso")
        except Exception as e:                               # noqa: BLE001
            ex.log(1, f"conferência do Razão com os totais do SAP não feita: {e}"[:600], "aviso")
        if balancete := baixar_balancete_sap(ex, pasta, meses, carimbo):
            guardar(ex, 1, "balancete", balancete, hoje, carimbo)

        # 2. conversão
        ex.etapa(2, "andamento", inicio=True)
        arquivos, resumo = montar_planilhas(extracao, pasta, carimbo, ex)
        segurados = resumo["segurados"]
        if not a.ensaio:
            import robo_banco
            robo_banco.pendencias(pasta)
        tot = {k: round(sum(x[k] for x in arquivos), 2) for k in ("linhas", "lancamentos", "debito", "credito")}
        nota = (f"{len(arquivos)} planilha(s), {int(tot['linhas'])} linhas, {int(tot['lancamentos'])} lançamentos, "
                f"D = C R$ {tot['debito']:,.2f}; {len(segurados)} documento(s) segurado(s)")
        ex.etapa(2, "sucesso", nota=nota)
        ex.log(2, nota + "; " + ", ".join(f"{os.path.basename(x['arquivo'])} ({x['linhas']} linhas)" for x in arquivos))
        if segurados:
            ex.log(2, f"{len(segurados)} documento(s) segurado(s) por conta SAP sem conta ERP (ver Pendências)", "aviso")
        campos = {"docs_extraidos": resumo["docs_extraidos"], "docs_segurados": len(segurados),
                  "lancamentos": int(tot["lancamentos"]), "linhas": int(tot["linhas"]), "partes": len(arquivos),
                  "debito": tot["debito"], "credito": tot["credito"], "avisos": resumo["avisos"][:20],
                  "lote": arquivos[0]["lote"] if arquivos else None}
        if a.sem_erp:
            ex.log(2, "(teste) parado depois da conversão: " + json.dumps(arquivos, ensure_ascii=False))
            ex.fim("sucesso", **campos)
            return 0
        if len(arquivos) == 1:
            guardar(ex, 2, "planilha", arquivos[0]["arquivo"], hoje, carimbo)
        elif arquivos:
            import zipfile
            pacote = os.path.join(pasta, f"CONTABIL_{arquivos[0]['lote']}-{arquivos[-1]['lote']}_{carimbo}.zip")
            with zipfile.ZipFile(pacote, "w") as z:
                for x in arquivos:
                    z.write(x["arquivo"], os.path.basename(x["arquivo"]))
            guardar(ex, 2, "planilha", pacote, hoje, carimbo)
        if not arquivos:
            ex.log(4, "nenhum documento novo para importar")
            ex.fim("pendencias" if segurados else "sem", docs_novos=0, **campos)
            return 0

        # 3 e 4. envio e importação na ERP (robô de tela)
        pedido = os.path.join(pasta, "pedido.json")
        json.dump({"pasta": os.path.join(pasta, "prints"), "ensaio": a.ensaio,
                   "arquivos": [{"arquivo": x["arquivo"], "de": x["de"], "ate": x["ate"]} for x in arquivos]},
                  open(pedido, "w"), ensure_ascii=False)
        if not a.ensaio:
            json.dump({"execucao": ex.id, "arquivos": arquivos}, open(PENDENTE, "w"), ensure_ascii=False, indent=1)
        ex.etapa(3, "andamento", inicio=True)
        for tentativa in range(1, 4):
            codigo, eventos = rodar_importador(ex, pedido, arquivos)
            if codigo != 11:
                break
            ex.log(3, f"login recusado na ERP (senha recusada pela ERP Cloud ou sessão do robo-importa ainda "
                      f"aberta); nova tentativa em 15 min ({tentativa}/3)", "aviso")
            time.sleep(900)
        if codigo == 11:
            codigo = 10
        sucesso = {e["arquivo"] for e in eventos if e["ev"] == "sucesso"}

        if a.ensaio:
            ok = codigo == 0 and sum(1 for e in eventos if e["ev"].startswith("ensaio")) == len(arquivos)
            ex.fim("sucesso" if ok else "erro", **campos)
            return 0 if ok else 3

        # conferência pela API e marcação no portal
        import robo_banco
        importados, problemas = 0, []
        for x in arquivos:
            nome = os.path.basename(x["arquivo"])
            if nome not in sucesso:
                continue
            c = conferir_lote(x["ano"], x["lote"], x)
            if c and c["confere"]:
                robo_banco.importado(pasta, x["lote"], x["arquivo"].replace(".xlsx", ".docs.json"))
                x["ok"] = "gravou"
                importados += x["lancamentos"]
                ex.log(4, f"lote {x['lote']} conferido pela API: {c['linhas']} partidas, {c['lancamentos']} "
                          f"lançamentos, D = C R$ {c['debito']:,.2f}")
            else:
                problemas.append(f"lote {x['lote']} não confere pela API: {c}")
                ex.log(4, problemas[-1], "erro")
        nao_tentados = [x for x in arquivos if os.path.basename(x["arquivo"]) not in sucesso]
        if codigo == 20 or problemas:
            json.dump({"execucao": ex.id, "arquivos": arquivos}, open(PENDENTE, "w"), ensure_ascii=False, indent=1)
            ex.etapa(4, "erro", nota="; ".join(problemas) or "importação sem \"Sucesso\": conferir na ERP")
            ex.fim("verificar", docs_novos=importados, observacao="Importação sem confirmação. A próxima execução "
                   "confere o lote pela API antes de continuar.", **campos)
            return 2
        os.remove(PENDENTE)
        if nao_tentados:
            ex.etapa(4, "erro", nota=f"{len(nao_tentados)} planilha(s) não importada(s): o robô parou antes de "
                                     "confirmar; os documentos entram na próxima execução")
            ex.fim("erro", docs_novos=importados, **campos)
            return 3
        ex.etapa(4, "sucesso", nota=f"{len(arquivos)} lote(s) importado(s) e conferido(s): "
                                    + ", ".join(str(x["lote"]) for x in arquivos))
        ex.fim("pendencias" if segurados else "sucesso", docs_novos=importados, **campos)
        return 0
    except Exception as e:                                   # noqa: BLE001
        traceback.print_exc()
        ex.log(4, f"erro: {e}"[:1500], "erro")
        ex.fim("erro", observacao=str(e)[:500])
        return 3


if __name__ == "__main__":
    sys.exit(main())
