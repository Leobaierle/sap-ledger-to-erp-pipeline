"""Leva ao banco do portal (Supabase, schema contabil) o resultado do montar_lotes.py e das gravações na ERP.

  robo_banco.py pendencias PASTA_LOTES          -> robo_pendencia só de contas (substitui as da sigla) + robo_segurado
                                                   (upsert); CC sem de-para não é pendência (sai 0, como a planilha)
  robo_banco.py importado PASTA_LOTES LOTE [ARQ] -> robo_documento com os documentos do lote (só depois de conferido
                                                   na ERP) e libera os segurados que entraram nele; ARQ = .docs.json
                                                   (padrão lote_<LOTE>.docs.json; planilha: CONTABIL_<LOTE>.docs.json)
  robo_banco.py limpar-lotes DE ATE             -> tira de robo_documento os lotes DE..ATE (lotes excluídos na ERP)
  robo_banco.py execucao ARQ.json               -> grava uma execução (robo_execucao + robo_etapa + robo_log) com os
                                                   dados e horários do arquivo; devolve o id
Precisa de DATABASE_URL.
"""
import json
import os
import sys
from collections import defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "app"))
import tabelas  # noqa: E402

SIGLA = "EMP"


def pendencias(pasta):
    r = json.load(open(os.path.join(pasta, "resumo.json")))
    docs_conta = defaultdict(int)
    for s in r["segurados"]:
        for c in s["contas_sap"]:
            docs_conta[c] += 1
    with tabelas._conectar() as con, con.transaction():
        con.execute("delete from contabil.robo_pendencia where sigla = %s", (SIGLA,))
        # CC sem de-para não segura mais o documento (sai 0, como a planilha — 16/10/2026): quem estava preso só por CC
        # sai da lista e entra na próxima execução pela janela do mês
        soltos = con.execute("delete from contabil.robo_segurado where sigla = %s and liberado_em is null and "
                             "cardinality(contas_sap) = 0", (SIGLA,)).rowcount
        for p in r["pend_contas"]:
            con.execute("insert into contabil.robo_pendencia (sigla, tipo, codigo_sap, nome_sap, docs, linhas, debito, "
                        "credito, historico_exemplo) values (%s, 'conta', %s, %s, %s, %s, %s, %s, %s)",
                        (SIGLA, p["conta"], p.get("nome_sap", ""), docs_conta[p["conta"]], p["linhas"],
                         round(p["debito"], 2), round(p["credito"], 2), p.get("exemplo", "")))
        for s in r["segurados"]:
            con.execute("insert into contabil.robo_segurado (sigla, doc, ano, data_lancamento, valor, contas_sap, ccs_sap, "
                        "linhas, desde) values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, current_date) "
                        "on conflict (sigla, doc, ano) do update set valor = excluded.valor, contas_sap = "
                        "excluded.contas_sap, ccs_sap = excluded.ccs_sap, linhas = excluded.linhas",
                        (SIGLA, s["doc"], int(s["data"][:4]), s["data"], s["debito"], s["contas_sap"], s["ccs_sap"],
                         json.dumps(s.get("linhas", []), ensure_ascii=False)))
    print(f"pendências: {len(r['pend_contas'])} conta(s); segurados: {len(r['segurados'])}; "
          f"{soltos} documento(s) presos só por CC voltaram para a fila normal")


def importado(pasta, lote, arquivo=None):
    docs = json.load(open(arquivo or os.path.join(pasta, f"lote_{lote}.docs.json")))
    with tabelas._conectar() as con, con.transaction():
        for d in docs:
            con.execute("insert into contabil.robo_documento (sigla, doc, ano, data_lancamento, lote, referencia, textos) "
                        "values (%s, %s, %s, %s, %s, %s, %s) on conflict (sigla, doc, ano) do nothing",
                        (SIGLA, d["doc"], int(d["data"][:4]), d["data"], int(lote), d["ref"],
                         json.dumps(d["textos"], ensure_ascii=False)))
        n = con.execute("update contabil.robo_segurado set liberado_em = now() where sigla = %s and liberado_em is null "
                        "and doc = any(%s)", (SIGLA, [d["doc"] for d in docs])).rowcount
    msg = f"lote {lote}: {len(docs)} documento(s) marcados como importados; {n} segurado(s) liberado(s)"
    print(msg)
    return msg


def limpar_lotes(de, ate):
    with tabelas._conectar() as con, con.transaction():
        n = con.execute("delete from contabil.robo_documento where sigla = %s and lote between %s and %s",
                        (SIGLA, int(de), int(ate))).rowcount
    print(f"lotes {de} a {ate}: {n} documento(s) tirados de robo_documento")


CAMPOS_EXEC = ("data", "status", "periodo_de", "periodo_ate", "iniciado_em", "terminado_em", "docs_extraidos",
               "docs_novos", "docs_segurados", "lancamentos", "linhas", "partes", "debito", "credito", "lote",
               "observacao")


def execucao(arquivo):
    e = json.load(open(arquivo))
    campos = [c for c in CAMPOS_EXEC if c in e]
    with tabelas._conectar() as con, con.transaction():
        if con.execute("select 1 from contabil.robo_execucao where sigla = %s and data = %s and iniciado_em = %s",
                       (SIGLA, e["data"], e["iniciado_em"])).fetchone():
            sys.exit("execução já registrada (mesma data e início)")
        eid = con.execute(f"insert into contabil.robo_execucao (sigla, avisos, {', '.join(campos)}) values "
                          f"(%s, %s::jsonb, {', '.join(['%s'] * len(campos))}) returning id",
                          (SIGLA, json.dumps(e.get("avisos", []), ensure_ascii=False), *[e[c] for c in campos])).fetchone()[0]
        for et in e.get("etapas", []):
            con.execute("insert into contabil.robo_etapa (execucao_id, n, status, iniciado_em, terminado_em, nota) "
                        "values (%s, %s, %s, %s, %s, %s)",
                        (eid, et["n"], et["status"], et.get("iniciado_em"), et.get("terminado_em"), et.get("nota", "")))
        for lg in e.get("log", []):
            con.execute("insert into contabil.robo_log (execucao_id, quando, nivel, etapa, mensagem) values "
                        "(%s, %s, %s, %s, %s)", (eid, lg["quando"], lg["nivel"], lg["etapa"], lg["mensagem"]))
    print(f"execução {eid} registrada: {e['data']} {e['status']}, {len(e.get('etapas', []))} etapa(s), "
          f"{len(e.get('log', []))} linha(s) de log")
    return eid


if __name__ == "__main__":
    {"pendencias": lambda: pendencias(sys.argv[2]),
     "importado": lambda: importado(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None),
     "limpar-lotes": lambda: limpar_lotes(sys.argv[2], sys.argv[3]),
     "execucao": lambda: execucao(sys.argv[2])}[sys.argv[1]]()
