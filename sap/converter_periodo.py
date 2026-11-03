"""Monta o Razão SAP a partir da extração RFC e converte com o conversor do conversor contábil (mesmo código/tabelas).
Uso: converter_periodo.py PASTA_EXTRACAO TABELAS_DIR DESTINO_DIR NOME"""
import csv, json, os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conversor
from montar_razao import linhas, CAB
from openpyxl import Workbook

pasta, tab, destino, nome = sys.argv[1:5]
os.makedirs(destino, exist_ok=True)
rows = linhas(pasta)

razao = os.path.join(destino, f"RAZÃO {nome} - extraído do SAP.xlsx")
wb = Workbook(write_only=True)
ws = wb.create_sheet("Sheet1")
ws.append(CAB)
for r in rows:
    ws.append([r[c] for c in CAB])
wb.save(razao)
print("razão:", razao, len(rows), "linhas")

plano = json.load(open(f"{tab}/plano.json"))["linhas"]
cc = json.load(open(f"{tab}/cc.json"))["linhas"]
contas = list(csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "dados", "contas_sap.csv"), encoding="utf-8")))
tabelas = conversor.montar_tabelas(plano, cc, contas)

res = conversor.converter(razao, tabelas=tabelas)
print("linhas SAP:", res.total_sap, "| zeradas:", res.zeradas, "| linhas ERP:", len(res.linhas), "| lançamentos:", res.lancamentos)
print("período:", res.periodo, "| débito:", round(res.total_debito, 2), "| crédito:", round(res.total_credito, 2))
print("partes:", res.partes)
print("erros:", res.erros[:10])
print("avisos:", [a[:250] for a in res.avisos[:10]])
print("contas SAP sem conta ERP:", res.pend_contas[:20])
print("contas duplicadas:", res.pend_duplicadas[:10])
print("CC sem de-para:", res.pend_cc[:20])
if res.bloqueado:
    print("BLOQUEADO: arquivo de importação não gerado")
else:
    saida = os.path.join(destino, f"IMPORTAÇÃO {nome}.xlsx")
    conversor.gravar_xlsx(res, saida, lote_inicial=conversor.lote_base(res))
    print("importação:", saida, "lote inicial", conversor.lote_base(res))
