"""Compara um mês já importado na ERP com o que o robô geraria hoje a partir do SAP. SÓ LEITURA.

  SAP (extração RFC) -> montar_razao -> conversor (tabelas de-para atuais, lidas do Supabase)
  x partidas gravadas na ERP (JSON lido antes pelo erp-api/erp_leitura.py)

Não grava em lugar nenhum além da pasta DESTINO (relatório). Não toca Supabase (só lê), ERP nem SAP.
Uso: comparar_mes.py PASTA_EXTRACAO PARTIDAS_ERP.json DESTINO
"""
import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "app"))
sys.path.insert(0, AQUI)
import conversor  # noqa: E402
import tabelas  # noqa: E402
from montar_razao import CAB, linhas  # noqa: E402
from openpyxl import Workbook  # noqa: E402

pasta, json_erp, destino = sys.argv[1:4]
os.makedirs(destino, exist_ok=True)
c2 = lambda v: round(float(v) + 0.0, 2)  # noqa: E731


def _data(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return (v.date() if isinstance(v, dt.datetime) else v).isoformat()
    s = str(v)
    return f"{s[6:10]}-{s[3:5]}-{s[0:2]}" if "/" in s else s[:10]


# — lado SAP: o que o robô geraria —
rows = linhas(pasta)
razao = os.path.join(destino, "RAZÃO extraído do SAP.xlsx")
wb = Workbook(write_only=True)
ws = wb.create_sheet("Sheet1")
ws.append(CAB)
for r in rows:
    ws.append([r[c] for c in CAB])
wb.save(razao)
res = conversor.converter(razao, tabelas=tabelas.carregar_para_conversao())
sap = [{"data": _data(l[3]), "conta": l[4], "tipo": l[2], "valor": c2(l[5]), "hist": str(l[6] or ""),
        "doc": str(l[7] or ""), "cc": l[8], "filial": l[10]} for l in res.linhas]

# — lado ERP: o que está gravado —
erp_bruto = json.load(open(json_erp))
erp = []
for e in erp_bruto:
    obs = e.get("entryObservation") or []
    hist = obs[0].get("description", "") if obs and isinstance(obs, list) else ""
    br = e.get("branch")
    erp.append({"data": _data(e["date"]), "conta": e.get("account"), "tipo": e.get("type"), "valor": c2(e["amount"]),
                 "hist": hist or "", "doc": str(e.get("document") or ""), "lote": e.get("_lote"),
                 "filial": br.get("branch") if isinstance(br, dict) else br})


def tot(ls):
    d = sum(x["valor"] for x in ls if x["tipo"] == "D")
    c = sum(x["valor"] for x in ls if x["tipo"] == "C")
    return {"partidas": len(ls), "debito": round(d, 2), "credito": round(c, 2)}


def agrupa(ls, chave):
    g = defaultdict(lambda: [0, 0.0])
    for x in ls:
        k = chave(x)
        g[k][0] += 1
        g[k][1] += x["valor"]
    return g


resumo = {"sap_razao_linhas": res.total_sap, "sap_lancamentos": res.lancamentos, "sap": tot(sap), "erp": tot(erp),
          "pend_contas": res.pend_contas, "pend_cc": [{k: v for k, v in p.items() if k != "exemplo"} for p in res.pend_cc],
          "avisos": res.avisos[:20], "erros": res.erros[:20]}

# por conta e D/C
diffs_conta = []
gs, gr = agrupa(sap, lambda x: (x["conta"], x["tipo"])), agrupa(erp, lambda x: (x["conta"], x["tipo"]))
for k in sorted(set(gs) | set(gr), key=lambda k: (str(k[0]), k[1])):
    a, b = gs.get(k, [0, 0.0]), gr.get(k, [0, 0.0])
    if a[0] != b[0] or abs(a[1] - b[1]) > 0.005:
        diffs_conta.append({"conta": k[0], "tipo": k[1], "sap_n": a[0], "sap_valor": round(a[1], 2),
                            "erp_n": b[0], "erp_valor": round(b[1], 2), "dif": round(a[1] - b[1], 2)})

# por dia
diffs_dia = []
gs, gr = agrupa(sap, lambda x: (x["data"], x["tipo"])), agrupa(erp, lambda x: (x["data"], x["tipo"]))
for k in sorted(set(gs) | set(gr)):
    a, b = gs.get(k, [0, 0.0]), gr.get(k, [0, 0.0])
    if a[0] != b[0] or abs(a[1] - b[1]) > 0.005:
        diffs_dia.append({"data": k[0], "tipo": k[1], "sap_n": a[0], "sap_valor": round(a[1], 2), "erp_n": b[0],
                          "erp_valor": round(b[1], 2), "dif": round(a[1] - b[1], 2)})

# partida a partida: (data, conta, D/C, valor) e, para as que casam, o histórico
chave = lambda x: (x["data"], x["conta"], x["tipo"], x["valor"])  # noqa: E731
cs, cr = Counter(map(chave, sap)), Counter(map(chave, erp))
so_sap, so_erp = cs - cr, cr - cs
ex_sap = defaultdict(list)
for x in sap:
    if so_sap.get(chave(x)) and len(ex_sap[chave(x)]) < so_sap[chave(x)]:
        ex_sap[chave(x)].append(x)
ex_erp = defaultdict(list)
for x in erp:
    if so_erp.get(chave(x)) and len(ex_erp[chave(x)]) < so_erp[chave(x)]:
        ex_erp[chave(x)].append(x)
hist_s = Counter((chave(x), x["hist"].strip()) for x in sap)
hist_r = Counter((chave(x), x["hist"].strip()) for x in erp)
hist_dif = sum((hist_s - hist_r).values())

resumo["partidas_so_no_sap"] = sum(so_sap.values())
resumo["partidas_so_na_erp"] = sum(so_erp.values())
resumo["partidas_iguais_valor_conta_data"] = sum((cs & cr).values())
resumo["historicos_diferentes"] = hist_dif
resumo["contas_com_diferenca"] = len(diffs_conta)
resumo["dias_com_diferenca"] = len(diffs_dia)
json.dump(resumo, open(os.path.join(destino, "resumo.json"), "w"), ensure_ascii=False, indent=1, default=str)

# relatório
wb = Workbook(write_only=True)
for nome, dados in [("por conta", diffs_conta), ("por dia", diffs_dia),
                    ("só no SAP", [x for v in ex_sap.values() for x in v]),
                    ("só na ERP", [x for v in ex_erp.values() for x in v]),
                    ("históricos", [{"data": k[0][0], "conta": k[0][1], "tipo": k[0][2], "valor": k[0][3],
                                     "hist_sap": k[1], "n": n} for k, n in list((hist_s - hist_r).items())[:5000]])]:
    ws = wb.create_sheet(nome)
    if dados:
        cab = list(dados[0].keys())
        ws.append(cab)
        for d in dados:
            ws.append([d.get(c) for c in cab])
wb.save(os.path.join(destino, "COMPARAÇÃO SAP x ERP.xlsx"))
print(json.dumps({k: v for k, v in resumo.items() if k not in ("avisos", "pend_cc")}, ensure_ascii=False, indent=1, default=str))
