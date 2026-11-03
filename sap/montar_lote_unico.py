"""Monta UM lote da ERP (todos os lançamentos do período) dividido em partes de até 500 partidas. NÃO ENVIA NADA.

Decisão do usuário (16/10/2026): todas as importações do mês no mesmo lote (outubro/2026 = 1000001). A API corta em
60 s / ~1 MB, então o lote vai em várias chamadas do insert com o mesmo número (gravar_lote_unico.py).

Uso: montar_lote_unico.py PASTA_EXTRACAO DESTINO LOTE [--ate AAAAMMDD] [--data-lote AAAA-MM-DD] [--descricao TXT]
                          [--excluir-importados] [--lanc-inicial N]
Grava em DESTINO: parte_NNN.json (corpo do insert), parte_NNN.docs.json e resumo.json (segurados + linhas do SAP, para
o sap/robo_banco.py pendencias). Regras de conversão em sap/lotes.py (por_dia=False: dias misturados no mesmo lote).
"""
import argparse
import datetime as dt
import hashlib
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
ap.add_argument("lote", type=int)
ap.add_argument("--ate", help="última data de lançamento (AAAAMMDD), inclusive")
ap.add_argument("--data-lote", help="data do lote (padrão: último dia do mês, como os lotes de 09/2026)")
ap.add_argument("--descricao", help="descrição do lote (padrão: SAP MM/AAAA)")
ap.add_argument("--excluir-importados", action="store_true")
ap.add_argument("--lanc-inicial", type=int, default=1, help="número do 1º lançamento (continua um lote existente)")
a = ap.parse_args()
os.makedirs(a.destino, exist_ok=True)
assert not any(f.startswith("parte_") for f in os.listdir(a.destino)), f"{a.destino} já tem partes montadas"

with tabelas._conectar() as con:
    importados = {d for (d,) in con.execute("select doc from contabil.robo_documento where sigla = %s",
                                             (lotes.SIGLA,))} if a.excluir_importados else set()
    sem_rateio = {c for (c,) in con.execute("select conta from contabil.robo_conta_sem_rateio where sigla = %s",
                                             (lotes.SIGLA,))}

grupos, segurados, resumo = lotes.montar(
    linhas(a.pasta), tabelas.carregar_para_conversao(), sem_rateio, importados,
    dt.datetime.strptime(a.ate, "%Y%m%d").date() if a.ate else None, lotes.MAX_PARTIDAS, por_dia=False)
if not grupos:
    sys.exit("nada a importar")
ultima = grupos[0][0]
if a.data_lote:
    data_lote = dt.date.fromisoformat(a.data_lote)
else:
    prox = (ultima.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    data_lote = prox - dt.timedelta(days=1)
descricao = a.descricao or f"SAP {ultima.strftime('%m/%Y')}"

resumo["segurados"] = segurados
resumo["lote"] = a.lote
resumo["partes"] = []
seq = a.lanc_inicial
for i, (_data, grupo, _k, _total) in enumerate(grupos, 1):
    entradas = []
    for l in grupo:
        entradas += [{**e, "number": seq} for e in l["partidas"]]
        seq += 1
    corpo = {"payload": {"accountingLotNumber": a.lote, "accountingLotDate": data_lote.isoformat(),
                         "accountingLotType": "M", "accountingLotDescription": descricao,
                         "accountingEntry": entradas}}
    bruto = json.dumps(corpo, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    deb = round(sum(e["amount"] for e in entradas if e["type"] == "D"), 2)
    cre = round(sum(e["amount"] for e in entradas if e["type"] == "C"), 2)
    datas = sorted({e["date"] for e in entradas})
    docs = [{"doc": l["doc"], "ref": l["ref"], "textos": l["textos"], "data": l["partidas"][0]["date"]} for l in grupo]
    json.dump(corpo, open(os.path.join(a.destino, f"parte_{i:03d}.json"), "w"), ensure_ascii=False)
    json.dump(docs, open(os.path.join(a.destino, f"parte_{i:03d}.docs.json"), "w"), ensure_ascii=False)
    resumo["partes"].append({"parte": i, "lancamentos": len(grupo), "partidas": len(entradas), "debito": deb,
                             "credito": cre, "datas": [datas[0], datas[-1]], "bytes": len(bruto),
                             "sha256": hashlib.sha256(bruto).hexdigest()})
json.dump(resumo, open(os.path.join(a.destino, "resumo.json"), "w"), ensure_ascii=False, indent=1, default=str)

ps = resumo["partes"]
print(f"lote {a.lote} ({descricao}, data {data_lote:%d/%m/%Y}): {len(ps)} partes, "
      f"{sum(p['lancamentos'] for p in ps)} lançamentos, {sum(p['partidas'] for p in ps)} partidas, "
      f"D {sum(p['debito'] for p in ps):,.2f} C {sum(p['credito'] for p in ps):,.2f}, "
      f"maior parte {max(p['partidas'] for p in ps)} partidas / {max(p['bytes'] for p in ps) / 1e6:.2f} MB")
print(f"segurados: {len(segurados)} docs | fora do período: {resumo['fora_do_periodo']} lanç. | "
      f"CC sem de-para: {len(resumo['pend_ccs'])} | contas sem de-para: {len(resumo['pend_contas'])} | "
      f"já importadas: {resumo['ja_importadas']} linha(s)")
