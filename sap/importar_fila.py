"""Importação avulsa: grava na ERP os documentos que saíram de "segurado" quando a conta/CC foi preenchida no portal.

Roda no k3s como CronJob (a cada 2 min, um por vez). Cada execução atende UM pedido da contabil.robo_fila:
  segurados do pedido (linhas do SAP guardadas no banco) -> conversão com o de-para atual -> lotes de até 500
  partidas, numerados depois do maior lote 1000006–1099999 que existe na ERP -> grava e confere cada lote pela
  ERP API -> marca os documentos como importados.
Erro em qualquer passo: o pedido fica "erro" com a mensagem (aparece no portal) e nada é repetido sozinho.
Precisa de DATABASE_URL e ERP_TOKEN.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "app"))
sys.path.insert(0, AQUI)
import lotes  # noqa: E402
import erp  # noqa: E402
import tabelas  # noqa: E402

SIGLA = lotes.SIGLA


def log(msg):
    print(msg, flush=True)


def main():
    with tabelas._conectar() as con:
        # um por vez: o CronJob não sobrepõe execuções e nenhum pedido começa enquanto outro estiver "gravando"
        # (o Supavisor em modo transação não segura pg_advisory_lock de sessão)
        p = con.execute("update contabil.robo_fila set status = 'gravando', iniciado_em = now() where id = ("
                        "select id from contabil.robo_fila where sigla = %s and status = 'fila' order by id limit 1 "
                        "for update skip locked) and not exists (select 1 from contabil.robo_fila where status = "
                        "'gravando') returning id, docs", (SIGLA,)).fetchone()
    if not p:
        return
    pid, docs = p
    log(f"pedido {pid}: {len(docs)} documento(s)")
    feitos = []
    try:
        feitos = atender(docs, feitos)
        with tabelas._conectar() as con:
            if feitos:
                con.execute("update contabil.robo_fila set status = 'importado', terminado_em = now(), lotes = %s, "
                            "partidas = %s, debito = %s, mensagem = %s where id = %s",
                            ([f["lote"] for f in feitos], sum(f["partidas"] for f in feitos),
                             sum(f["debito"] for f in feitos), "", pid))
            else:
                con.execute("update contabil.robo_fila set status = 'vazio', terminado_em = now(), mensagem = %s "
                            "where id = %s", ("Nenhum documento liberado para importar (ainda falta de-para ou "
                                              "já foram importados).", pid))
    except Exception as e:  # noqa: BLE001 — qualquer erro vai para o portal
        log(f"ERRO: {e}")
        with tabelas._conectar() as con:
            con.execute("update contabil.robo_fila set status = 'erro', terminado_em = now(), lotes = %s, "
                        "mensagem = %s where id = %s", ([f["lote"] for f in feitos], str(e)[:1000], pid))
        sys.exit(1)


def atender(docs, feitos):
    with tabelas._conectar() as con:
        seg = con.execute("select doc, linhas from contabil.robo_segurado where sigla = %s and liberado_em is null "
                          "and doc = any(%s)", (SIGLA, docs)).fetchall()
        importados = {d for (d,) in con.execute("select doc from contabil.robo_documento where sigla = %s and "
                                                 "doc = any(%s)", (SIGLA, docs))}
        sem_rateio = {c for (c,) in con.execute("select conta from contabil.robo_conta_sem_rateio where sigla = %s",
                                                 (SIGLA,))}
    seg = sorted((s for s in seg if s[0] not in importados), key=lambda s: int(s[0]) if s[0].isdigit() else 0)
    rows = [lotes.linha_de_json(l) for _doc, ls in seg for l in ls]
    if not rows:
        return []
    grupos, ainda, _ = lotes.montar(rows, tabelas.carregar_para_conversao(), sem_rateio, por_dia=False)
    if ainda:
        log(f"{len(ainda)} documento(s) continuam segurados: {[s['doc'] for s in ainda]}")
    if not grupos:
        return []
    existentes = erp.lotes_existentes(SIGLA)
    proximo = max(existentes | {erp.LOTE_MIN - 1}) + 1

    def sem_rateio_novo(conta):
        with tabelas._conectar() as con:
            con.execute("insert into contabil.robo_conta_sem_rateio (sigla, conta) values (%s, %s) on conflict do nothing",
                        (SIGLA, conta))

    for corpo, info, docs_lote in lotes.numerar(grupos, proximo, existentes, descricao="SAP avulso"):
        conf = erp.gravar(SIGLA, corpo, sem_rateio_novo, log)
        with tabelas._conectar() as con, con.transaction():
            for d in docs_lote:
                con.execute("insert into contabil.robo_documento (sigla, doc, ano, data_lancamento, lote, referencia, "
                            "textos) values (%s, %s, %s, %s, %s, %s, %s::jsonb) on conflict (sigla, doc, ano) do nothing",
                            (SIGLA, d["doc"], int(d["data"][:4]), d["data"], conf["lote"], d["ref"],
                             lotes.json.dumps(d["textos"], ensure_ascii=False)))
            con.execute("update contabil.robo_segurado set liberado_em = now() where sigla = %s and doc = any(%s)",
                        (SIGLA, [d["doc"] for d in docs_lote]))
        log(f"lote {conf['lote']} conferido: {conf['partidas']} partidas, R$ {conf['debito']:,.2f}")
        feitos.append(conf)
    return feitos


if __name__ == "__main__":
    main()
