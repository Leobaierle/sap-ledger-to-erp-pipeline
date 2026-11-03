"""Monta os lotes da ERP (corpo do insert da ERP API) a partir das linhas do Razão. Não lê arquivo, não envia nada.

Usado pelo montar_lotes.py (linha de comando) e pelo importar_fila.py (importação avulsa no k3s).

Regras (ver README.md):
- 1 lote por dia de lançamento, dividido em lotes de até MAX_PARTIDAS sem quebrar lançamento;
- filial 1; histórico em 70 caracteres; documento = dígitos dos 9 últimos caracteres da Referência;
- rateio de centro de custo só nas contas ERP que aceitam (as que recusam ficam em contabil.robo_conta_sem_rateio);
- documento com conta SAP sem conta ERP fica SEGURADO (vai com as linhas do SAP, para converter de novo quando o
  de-para for preenchido);
- centro de custo SAP sem de-para sai 0, como a planilha manual (SOMASE sem correspondência) — decisão de 16/10/2026;
  não segura o documento, vira aviso no portal.
"""
import datetime as dt
import hashlib
import json
import re
from collections import OrderedDict, defaultdict

import conversor

FILIAL_ERP = 1          # em 09/2026 todas as partidas da EMP estão na filial 1
MAX_HISTORICO = 70       # a ERP guarda no máximo 70 caracteres
MAX_PARTIDAS = 500       # a ERP grava ~70 ms/partida e a API corta em 60 s (timeout); 500 ≈ 35 s. ~1 MB = HTTP 413
SIGLA = "EMP"


class ErroLotes(Exception):
    pass


def doc_sap(v):
    return str(int(float(v))) if re.fullmatch(r"[\d.]+", str(v).strip()) else str(v).strip()


def documento_erp(v):
    """Como a importação gravou em 09/2026: só os dígitos dos 9 últimos caracteres da Referência; sem dígito = 0."""
    d = re.sub(r"\D", "", str(v or ""))
    return int(d) if d else 0


def linha_json(r):
    """Linha do Razão (colunas do SAP) em JSON: datas viram texto."""
    return {k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v) for k, v in r.items() if k != "_ord"}


def linha_de_json(r):
    r = dict(r)
    if isinstance(r.get("Dt.lçto."), str):
        r["Dt.lçto."] = dt.date.fromisoformat(r["Dt.lçto."][:10])
    return r


def montar(rows, tabelas, sem_rateio=frozenset(), importados=frozenset(), ate=None, max_partidas=MAX_PARTIDAS,
           por_dia=True):
    """rows: linhas do Razão (colunas do SAP), em ordem de Nº doc. Devolve (grupos, segurados, resumo), onde cada
    grupo é (data, [lançamentos]) e cada lançamento {doc, ref, textos, partidas}; numerar() vira lotes.
    por_dia=False (importação avulsa): todos os dias no mesmo lote (data do lote = última data), como os lotes manuais
    de 09/2026, que misturavam dias."""
    por_doc = defaultdict(list)
    for r in rows:
        por_doc[doc_sap(r["Nº doc."])].append(r)

    lanc_doc, estado = {}, {"ant": object(), "n": 0}

    def coletar(_n, r):
        if r["doc"] != estado["ant"]:
            estado["n"] += 1
            estado["ant"] = r["doc"]
            lanc_doc[estado["n"]] = {"doc": doc_sap(r["doc"]), "ref": str(r["ref"] or ""), "textos": [],
                                     "contas": set(), "ccs": set()}
        info = lanc_doc[estado["n"]]
        info["contas"].add(conversor._cod(r["conta"]))
        if conversor._cod(r["cc"]) not in ("", "0"):
            info["ccs"].add(conversor._cod(r["cc"]))
        t = str(r["texto"] or "")
        if t and t not in info["textos"]:
            info["textos"].append(t)

    res = conversor.converter(None, tabelas=tabelas, coletar=coletar, excluir_docs=set(importados) or None,
                              linhas_sap=conversor.razao_de_linhas(rows))
    if res.erros or res.pend_duplicadas:
        raise ErroLotes(f"conversão com erro: {res.erros[:5]} {res.pend_duplicadas[:5]}")
    if importados:
        # o conversor pula os já importados, mas o coletar vê todos: refaz a numeração só com os que entraram
        lanc_doc = {i: v for i, v in enumerate((v for v in lanc_doc.values() if v["doc"] not in importados), 1)}
    pend_contas = {p["conta"] for p in res.pend_contas}
    pend_ccs = {p["cc"] for p in res.pend_cc}
    docs_cc = defaultdict(set)          # documentos com cada CC sem de-para (saem com CC 0)
    for v in lanc_doc.values():
        for c in v["ccs"] & pend_ccs:
            docs_cc[c].add(v["doc"])

    lancs = OrderedDict()
    for lanc, _partida, tipo, data, conta, valor, hist, documento, cc, vcc, _filial in res.linhas:
        lancs.setdefault(lanc, []).append((tipo, data, conta, round(valor, 2), hist, documento, cc, vcc))

    segurados, por_dia_, fora = [], defaultdict(list), 0
    for lanc, ps in lancs.items():
        info = lanc_doc[lanc]
        datas = {p[1] for p in ps}
        if len(datas) != 1:
            raise ErroLotes(f"documento {info['doc']} com mais de uma data: {datas}")
        data = datas.pop()
        if ate and data > ate:
            fora += 1
            continue
        if any(p[2] is None for p in ps):
            segurados.append({"doc": info["doc"], "data": data.isoformat(),
                              "debito": round(sum(p[3] for p in ps if p[0] == "D"), 2),
                              "contas_sap": sorted(info["contas"] & pend_contas),
                              "ccs_sap": [],
                              "linhas": [linha_json(r) for r in por_doc[info["doc"]]]})
            continue
        d = round(sum(p[3] for p in ps if p[0] == "D") - sum(p[3] for p in ps if p[0] == "C"), 2)
        if abs(d) > 0.005:
            raise ErroLotes(f"documento {info['doc']} com D≠C: {d}")
        entradas = []
        for tipo, _data, conta, valor, hist, documento, cc, vcc in ps:
            e = {"date": data.isoformat(), "amount": valor, "type": tipo, "account": int(conta),
                 "branch": FILIAL_ERP, "document": documento_erp(documento), "description": hist[:MAX_HISTORICO]}
            if cc not in ("", 0, None) and int(conta) not in sem_rateio:
                e["costCenters"] = [{"code": int(cc), "amount": round(float(vcc), 2)}]
            entradas.append(e)
        por_dia_[data].append({"doc": info["doc"], "ref": info["ref"], "textos": info["textos"], "partidas": entradas})

    grupos = []
    if not por_dia and por_dia_:
        por_dia_ = {max(por_dia_): [l for d in sorted(por_dia_) for l in por_dia_[d]]}
    for data in sorted(por_dia_):
        atuais, atual, n = [], [], 0
        for l in por_dia_[data]:
            if atual and n + len(l["partidas"]) > max_partidas:
                atuais.append(atual)
                atual, n = [], 0
            atual.append(l)
            n += len(l["partidas"])
        if atual:
            atuais.append(atual)
        grupos += [(data, g, i, len(atuais)) for i, g in enumerate(atuais, 1)]

    resumo = {"periodo": [min(por_dia_).isoformat(), max(por_dia_).isoformat()] if por_dia_ else None,
              "linhas_razao": res.total_sap, "fora_do_periodo": fora, "ja_importadas": res.ja_lancadas,
              "pend_contas": res.pend_contas, "pend_ccs": [{**p, "docs": len(docs_cc[p["cc"]])} for p in res.pend_cc],
              "avisos": res.avisos[:20]}
    return grupos, segurados, resumo


def numerar(grupos, proximo, pular=frozenset(), descricao="SAP"):
    """Dá número aos grupos (pulando os já usados) e devolve [(corpo do insert, info, documentos)]."""
    out = []
    numero = proximo
    for data, grupo, i, total in grupos:
        while numero in pular:
            numero += 1
        entradas = []
        for seq, l in enumerate(grupo, 1):
            entradas += [{**e, "number": seq} for e in l["partidas"]]
        desc = f"{descricao} {data.strftime('%d/%m/%Y')}" + (f" {i}/{total}" if total > 1 else "")
        corpo = {"payload": {"accountingLotNumber": numero, "accountingLotDate": data.isoformat(),
                             "accountingLotType": "D", "accountingLotDescription": desc, "accountingEntry": entradas}}
        bruto = json.dumps(corpo, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        deb = round(sum(e["amount"] for e in entradas if e["type"] == "D"), 2)
        cre = round(sum(e["amount"] for e in entradas if e["type"] == "C"), 2)
        info = {"lote": numero, "data": data.isoformat(), "descricao": desc, "lancamentos": len(grupo),
                "partidas": len(entradas), "debito": deb, "credito": cre,
                "com_centro_custo": sum(1 for e in entradas if "costCenters" in e),
                "bytes": len(bruto), "sha256": hashlib.sha256(bruto).hexdigest()}
        docs = [{"doc": l["doc"], "ref": l["ref"], "textos": l["textos"], "data": data.isoformat()} for l in grupo]
        out.append((corpo, info, docs))
        numero += 1
    return out
