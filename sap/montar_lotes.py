"""Monta os lotes da ERP (corpo da ERP API) a partir da extração RFC do SAP. NÃO ENVIA NADA.

  extração (bkpf/bseg/faglflexa .jsonl) -> montar_razao -> lotes.montar (conversor + de-para do Supabase)

Uso: montar_lotes.py PASTA_EXTRACAO DESTINO LOTE_INICIAL [--ate AAAAMMDD] [--max N] [--excluir-importados] [--pular L,L]
Grava em DESTINO: lote_<n>.json (corpo do insert), lote_<n>.docs.json (documentos SAP do lote) e resumo.json (com os
segurados e as linhas do SAP deles; o sap/robo_banco.py leva ao portal). Regras em sap/lotes.py.
Com --excluir-importados, os documentos já gravados (contabil.robo_documento) ficam de fora.
"""
import argparse
import datetime as dt
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "app"))
sys.path.insert(0, AQUI)
import lotes  # noqa: E402
import tabelas  # noqa: E402
from montar_razao import linhas  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("pasta")
ap.add_argument("destino")
ap.add_argument("lote_inicial", type=int)
ap.add_argument("--ate", help="última data de lançamento (AAAAMMDD), inclusive")
ap.add_argument("--max", type=int, default=lotes.MAX_PARTIDAS)
ap.add_argument("--excluir-importados", action="store_true")
ap.add_argument("--pular", default="", help="números de lote já usados, separados por vírgula")
a = ap.parse_args()
os.makedirs(a.destino, exist_ok=True)

with tabelas._conectar() as con:
    importados = {d for (d,) in con.execute("select doc from contabil.robo_documento where sigla = %s",
                                             (lotes.SIGLA,))} if a.excluir_importados else set()
    sem_rateio = {c for (c,) in con.execute("select conta from contabil.robo_conta_sem_rateio where sigla = %s",
                                             (lotes.SIGLA,))}

grupos, segurados, resumo = lotes.montar(
    linhas(a.pasta), tabelas.carregar_para_conversao(), sem_rateio, importados,
    dt.datetime.strptime(a.ate, "%Y%m%d").date() if a.ate else None, a.max)
resumo["segurados"] = segurados
resumo["lotes"] = []
for corpo, info, docs in lotes.numerar(grupos, a.lote_inicial, {int(x) for x in a.pular.split(",") if x.strip()}):
    json.dump(corpo, open(os.path.join(a.destino, f"lote_{info['lote']}.json"), "w"), ensure_ascii=False)
    json.dump(docs, open(os.path.join(a.destino, f"lote_{info['lote']}.docs.json"), "w"), ensure_ascii=False)
    resumo["lotes"].append(info)
json.dump(resumo, open(os.path.join(a.destino, "resumo.json"), "w"), ensure_ascii=False, indent=1, default=str)

for l in resumo["lotes"]:
    print(f"{l['lote']}  {l['data']}  {l['lancamentos']:>5} lanç.  {l['partidas']:>6} partidas  "
          f"D=C {l['debito']:>16,.2f}  {'OK' if abs(l['debito'] - l['credito']) < 0.005 else 'D≠C!'}  "
          f"{l['bytes'] / 1e6:.1f} MB")
print(f"segurados: {len(segurados)} docs | fora do período: {resumo['fora_do_periodo']} lanç. | "
      f"CC sem de-para: {len(resumo['pend_ccs'])} | já importadas: {resumo['ja_importadas']} linha(s)")
