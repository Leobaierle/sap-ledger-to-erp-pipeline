"""Gera as planilhas de importação da ERP (layout do site, app/conversor.py) a partir da extração RFC do SAP.
NÃO ENVIA NADA. Caminho da planilha + robô de tela (decisão de 16/10/2026: a API junta os lançamentos do mesmo dia).

Uso: gerar_planilhas.py PASTA_EXTRACAO DESTINO LOTE_INICIAL [--partes N] [--excluir-importados]

- Documentos com conta SAP sem conta ERP ficam SEGURADOS (sap/lotes.py): saem da planilha e vão para o resumo.json
  (o sap/robo_banco.py pendencias leva ao portal). CC SAP sem de-para sai 0, como a planilha manual (16/10/2026).
- Um arquivo por lote: CONTABIL_<lote>.xlsx, uma aba só, lançamentos inteiros. --partes N divide em N arquivos de
  tamanho parecido (padrão: o mínimo, até 49.998 linhas cada, o maior já importado).
- Com --excluir-importados, os documentos de contabil.robo_documento ficam de fora (só quando o banco estiver em dia).
"""
import argparse
import json
import math
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "app"))
sys.path.insert(0, AQUI)
import conversor  # noqa: E402
import lotes  # noqa: E402
import tabelas  # noqa: E402
from montar_razao import linhas  # noqa: E402
from xlsx_rapido import Planilha, gravar  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("pasta")
ap.add_argument("destino")
ap.add_argument("lote_inicial", type=int)
ap.add_argument("--partes", type=int)
ap.add_argument("--excluir-importados", action="store_true")
a = ap.parse_args()
os.makedirs(a.destino, exist_ok=True)
assert not any(f.startswith("CONTABIL_") for f in os.listdir(a.destino)), f"{a.destino} já tem planilhas"

with tabelas._conectar() as con:
    importados = {d for (d,) in con.execute("select doc from contabil.robo_documento where sigla = %s",
                                             (lotes.SIGLA,))} if a.excluir_importados else set()
    sem_rateio = {c for (c,) in con.execute("select conta from contabil.robo_conta_sem_rateio where sigla = %s",
                                             (lotes.SIGLA,))}
tab = tabelas.carregar_para_conversao()
rows = list(linhas(a.pasta))

# mesmos segurados do robô (conta sem de-para / CC sem de-para)
_g, segurados, resumo = lotes.montar(rows, tab, sem_rateio, importados)
fora = {conversor._cod(s["doc"]) for s in segurados} | {conversor._cod(d) for d in importados}

razao = list(conversor.razao_de_linhas(rows))
res = conversor.converter(None, tabelas=tab, excluir_docs=fora or None, linhas_sap=razao)
# lançamento -> documento SAP, pela mesma regra do conversor (novo lançamento quando o Nº doc. muda)
doc_do_lanc, ant, n = {}, object(), 0
info_doc = {}   # Referência e textos de cada documento (o portal compara com o SAP para achar os alterados)
for r in razao:
    d = conversor._cod(r["doc"])
    if d in fora:
        continue
    if r["doc"] != ant:
        n += 1
        ant = r["doc"]
    doc_do_lanc[n] = d
    i = info_doc.setdefault(d, {"ref": str(r["ref"] or ""), "textos": []})
    t = str(r["texto"] or "")
    if t and t not in i["textos"]:
        i["textos"].append(t)
if res.erros or res.pend_duplicadas or res.pend_contas or res.bloqueado:
    sys.exit(f"PARADO: conversão com erro/pendência: {res.erros[:5]} {res.pend_duplicadas[:5]} {res.pend_contas[:5]}")
# CC sem de-para sai 0, como a planilha manual (decisão de 16/10/2026): só avisa
cc0 = sum(1 for x in res.linhas if x[8] == 0)
if not res.linhas:
    sys.exit("nada a importar")

limite = conversor.LIMITE_LINHAS_PARTE
if a.partes:
    maior = max(sum(1 for _ in g) for _k, g in __import__("itertools").groupby(x[0] for x in res.linhas))
    limite = min(limite, math.ceil(len(res.linhas) / a.partes) + maior)
partes = conversor.dividir(res.linhas, limite)

base = conversor.dt.date(1899, 12, 30)
larguras = [15, 20, 26, 26, 30, 15, 18, 75, 20, 13, 20, 15]
estilos = [2, 2, 2, 2, 3, 2, 4, 5, 2, 2, 4, 2]
resumo["segurados"] = segurados
resumo["arquivos"] = []
for i, (ini, fim) in enumerate(partes):
    lote = a.lote_inicial + i
    sel = res.linhas[ini:fim]
    p = Planilha(f"{i + 1}° IMPORTAÇÃO", larguras, estilos)
    p.cabecalho = conversor.CABECALHO_ERP
    p.linhas = ([lote, lanc, partida, tipo, (data - base).days, conta, valor, hist, doc, cc, vcc, filial]
                for lanc, partida, tipo, data, conta, valor, hist, doc, cc, vcc, filial in sel)
    p.n_linhas = fim - ini
    nome = f"CONTABIL_{lote}.xlsx"
    gravar(os.path.join(a.destino, nome), [p])
    deb = round(sum(x[5] for x in sel if x[2] == "D"), 2)
    cre = round(sum(x[5] for x in sel if x[2] == "C"), 2)
    datas = [min(x[3] for x in sel).isoformat(), max(x[3] for x in sel).isoformat()]
    resumo["arquivos"].append({"arquivo": nome, "lote": lote, "linhas": fim - ini,
                               "lancamentos": len({x[0] for x in sel}), "debito": deb, "credito": cre, "datas": datas})
    # documentos do arquivo (marcados como importados só depois da conferência do lote)
    datas_lanc = {x[0]: x[3] for x in sel}
    json.dump([{"doc": doc_do_lanc[l], "data": datas_lanc[l].isoformat(), **info_doc[doc_do_lanc[l]]}
               for l in sorted(datas_lanc)], open(os.path.join(a.destino, f"CONTABIL_{lote}.docs.json"), "w"),
              ensure_ascii=False)
resumo["periodo"] = [d.isoformat() for d in res.periodo] if res.periodo else None
json.dump(resumo, open(os.path.join(a.destino, "resumo.json"), "w"), ensure_ascii=False, indent=1, default=str)

for f in resumo["arquivos"]:
    print(f"{f['arquivo']}  lote {f['lote']}  {f['linhas']:>6} linhas  {f['lancamentos']:>5} lanç.  "
          f"{f['datas'][0]} a {f['datas'][1]}  D {f['debito']:,.2f}  C {f['credito']:,.2f}  "
          f"{'OK' if abs(f['debito'] - f['credito']) < 0.005 else 'D≠C!'}")
print(f"total: {len(res.linhas)} linhas, D {res.total_debito:,.2f} C {res.total_credito:,.2f} | segurados: "
      f"{len(segurados)} docs | já importados fora: {len(importados)} | partidas com CC 0: {cc0} | avisos: {len(res.avisos)}")
