"""Extração SOMENTE LEITURA do razão da ACME (empresa definida em SAP_BUKRS) por RFC_READ_TABLE.

Uso: extrair_razao.py AAAAMMDD AAAAMMDD [--fagl]
Grava em /tmp/sap-saida/: bkpf.jsonl, bseg.jsonl (e faglflexa.jsonl + bsis.jsonl com --fagl), um por dia de lançamento.
Com --fagl também o balancete, lido no fim da extração: faglflext.jsonl (totais do ledger 0L por conta, divisão e
débito/crédito: saldo de abertura HSLVT + movimento HSL01..HSL12 de cada ano da janela) e skat.jsonl (nome das contas).
BSIS: Referência (XBLNR) de cada linha — é dela que a lista do SAP (FAGLL03) tira a Referência; o cabeçalho (BKPF) só
vale para linha que não está na BSIS (validado em 16/10/2026: documentos MB1B com a linha de estoque sem Referência).
"""
import json
import os
import sys
import time
import datetime as dt
from sap_rfc import Conexao

BUKRS = os.environ.get("SAP_BUKRS", "1000")   # empresa (company code)
LOTE = 40          # documentos por consulta de partidas
PAGINA = 20000     # linhas por página de RFC_READ_TABLE
SAIDA = os.environ.get("SAP_SAIDA", "/tmp/sap-saida")

C_BKPF = ["BELNR", "GJAHR", "BLART", "BUDAT", "BLDAT", "XBLNR", "BKTXT", "STBLG"]
C_BSEG = ["BELNR", "GJAHR", "BUZEI", "BSCHL", "HKONT", "SHKZG", "DMBTR", "GSBER", "KOSTL", "PRCTR",
          "MATNR", "WERKS", "ZUONR", "SGTXT"]
C_FAGL = ["DOCNR", "RYEAR", "BUZEI", "DOCLN", "RACCT", "DRCRK", "HSL", "RBUSA", "RCNTR", "PRCTR", "SEGMENT"]
C_BSIS = ["BELNR", "GJAHR", "BUZEI", "XBLNR"]
C_FLEXT = ["RYEAR", "RACCT", "RBUSA", "DRCRK", "HSLVT"] + [f"HSL{m:02d}" for m in range(1, 13)]
SO_RSTRIP = {"SGTXT"}   # o texto pode começar com espaço (a lista do SAP e o Excel mantêm)

sap = Conexao()


def ler(tab, campos, where):
    """RFC_READ_TABLE paginado (ROWSKIPS/ROWCOUNT)."""
    opts = []
    for w in where:
        while w:
            corte = len(w) if len(w) <= 72 else (w.rfind(",", 0, 72) + 1 or 72)
            opts.append({"TEXT": w[:corte]})
            w = w[corte:]
    tudo, pulo = [], 0
    while True:
        r = sap.call("RFC_READ_TABLE", QUERY_TABLE=tab, OPTIONS=opts, ROWSKIPS=str(pulo), ROWCOUNT=str(PAGINA),
                     FIELDS=[{"FIELDNAME": f} for f in campos], DATA=[])
        spec = [(f["FIELDNAME"], int(f["OFFSET"]), int(f["LENGTH"])) for f in r["FIELDS"]]
        dados = r.get("DATA") or []
        tudo += [{n: d["WA"][o:o + l].rstrip() if n in SO_RSTRIP else d["WA"][o:o + l].strip() for n, o, l in spec}
                 for d in dados]
        if len(dados) < PAGINA:
            return tudo
        pulo += PAGINA


def em(campo, vals):
    return f"{campo} IN (" + ",".join(f"'{v}'" for v in vals) + ")"


def main():
    de = dt.datetime.strptime(sys.argv[1], "%Y%m%d").date()
    ate = dt.datetime.strptime(sys.argv[2], "%Y%m%d").date()
    fagl = "--fagl" in sys.argv
    os.makedirs(SAIDA, exist_ok=True)
    arqs = {n: open(f"{SAIDA}/{n}.jsonl", "w")
            for n in (["bkpf", "bseg"] + (["faglflexa", "bsis", "faglflext", "skat"] if fagl else []))}
    d = de
    while d <= ate:
        t = time.time()
        dia = d.strftime("%Y%m%d")
        cab = ler("BKPF", C_BKPF, [f"BUKRS = '{BUKRS}' AND BUDAT = '{dia}'"])
        nb = nf = 0
        for x in cab:
            arqs["bkpf"].write(json.dumps(x, ensure_ascii=False) + "\n")
        por_ano = {}
        for x in cab:
            por_ano.setdefault(x["GJAHR"], []).append(x["BELNR"])
        for ano, docs in por_ano.items():
            for i in range(0, len(docs), LOTE):
                lote = docs[i:i + LOTE]
                for x in ler("BSEG", C_BSEG, [f"BUKRS = '{BUKRS}' AND GJAHR = '{ano}' AND", em("BELNR", lote)]):
                    arqs["bseg"].write(json.dumps(x, ensure_ascii=False) + "\n")
                    nb += 1
                if fagl:
                    for x in ler("FAGLFLEXA", C_FAGL, [f"RLDNR = '0L' AND RBUKRS = '{BUKRS}' AND RYEAR = '{ano}' AND",
                                                       em("DOCNR", lote)]):
                        arqs["faglflexa"].write(json.dumps(x, ensure_ascii=False) + "\n")
                        nf += 1
        if fagl:
            for x in ler("BSIS", C_BSIS, [f"BUKRS = '{BUKRS}' AND BUDAT = '{dia}'"]):
                arqs["bsis"].write(json.dumps(x, ensure_ascii=False) + "\n")
        print(f"[dia] {dia}: {len(cab)} docs, {nb} partidas BSEG" + (f", {nf} FAGLFLEXA" if fagl else "")
              + f" ({time.time() - t:.0f}s)", flush=True)
        d += dt.timedelta(days=1)
    if fagl:
        t, n = time.time(), 0
        for ano in sorted({str(de.year), str(ate.year)}):
            for x in ler("FAGLFLEXT", C_FLEXT, [f"RLDNR = '0L' AND RBUKRS = '{BUKRS}' AND RYEAR = '{ano}'"]):
                arqs["faglflext"].write(json.dumps(x, ensure_ascii=False) + "\n")
                n += 1
        ktopl = ler("T001", ["KTOPL"], [f"BUKRS = '{BUKRS}'"])[0]["KTOPL"]
        for x in ler("SKAT", ["SAKNR", "TXT50"], [f"SPRAS = 'P' AND KTOPL = '{ktopl}'"]):
            arqs["skat"].write(json.dumps(x, ensure_ascii=False) + "\n")
        print(f"[balancete] {n} linhas FAGLFLEXT ({time.time() - t:.0f}s)", flush=True)
    for f in arqs.values():
        f.close()
    print("[fim] ok", flush=True)


main()
