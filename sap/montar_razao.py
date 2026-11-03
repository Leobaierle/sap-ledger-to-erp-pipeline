"""Monta as linhas do Razão SAP (como o FAGLL03 exporta) a partir de bkpf/bseg/faglflexa.jsonl.
Regra validada em 25/08/2026 contra o RAZÃO 08.2026.xlsx:
  linhas = FAGLFLEXA ledger 0L sem BUZEI 000 (linhas de split/balanceamento ficam de fora; itens
  estatísticos/solicitação de adiantamento nem estão na FAGLFLEXA); CC = RCNTR; texto/material/CL da BSEG
  (texto cortado no '|', como na lista do SAP); Referência = BSIS-XBLNR da linha (cabeçalho BKPF-XBLNR só para a
  linha que não está na BSIS) — validado em 16/10/2026.
Referência e Texto saem como o Excel os deixa ao abrir a exportação do SAP (excel_tipado): só dígitos vira número,
"123 -" vira -123, "09/2026" vira 01/09/2026, "23/08" e "4-1" viram data do ano corrente."""
import json, os, re, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from conversor import _como_excel

CAB = ["Nº doc.", "Referência", "Div", "Tip", "Dt.lçto.", "CL", "Mont.em MI", "MoedI", "LNeg", "Cen.",
       "Centro cst", "Material", "Cen.lucro", "Texto", "Segmento", "Razão"]


RE_NUM = re.compile(r"^\s*(-?)\s*(\d+)\s*(-?)\s*$")
RE_DATA = re.compile(r"^\s*(\d{1,2})([/-])(\d{1,2})(?:\2(\d{2}|\d{4}))?\s*$")
RE_MES_ANO = re.compile(r"^\s*(\d{1,2})([/-])(\d{4})\s*$")


def excel_tipado(s, ano=None):
    """O que o Excel (pt-BR) faz com o texto de uma célula ao abrir a exportação do SAP: número ou data; senão texto
    (com os espaços do começo). Validado em 16/10/2026 contra o Razão exportado pelo Matheus (Referência e Texto)."""
    ano = ano or dt.date.today().year
    if s.strip() in ("-", "+"):          # " -" sozinho chega como "-" (sem o espaço)
        return s.strip()
    m = RE_NUM.match(s)
    if m and not (m.group(1) and m.group(3)):
        v = float(int(m.group(2)))
        return -v if (m.group(1) or m.group(3)) else v
    m = RE_MES_ANO.match(s)
    if m and 1 <= int(m.group(1)) <= 12:
        return dt.date(int(m.group(3)), int(m.group(1)), 1)
    m = RE_DATA.match(s)
    if m:
        d, mes, a = int(m.group(1)), int(m.group(3)), m.group(4)
        a = ano if a is None else int(a) + (2000 if int(a) < 30 else 1900) if len(a) == 2 else int(a)
        try:
            return dt.date(a, mes, d)
        except ValueError:
            return s
    return s


def num(s):
    return -float(s[:-1]) if s.endswith("-") else float(s)


def linhas(pasta):
    jl = lambda n: [json.loads(l) for l in open(f"{pasta}/{n}.jsonl")]
    bkpf = {(x["BELNR"], x["GJAHR"]): x for x in jl("bkpf")}
    bseg = {(x["BELNR"], x["GJAHR"], x["BUZEI"]): x for x in jl("bseg")}
    bsis = {(x["BELNR"], x["GJAHR"], x["BUZEI"]): x["XBLNR"] for x in jl("bsis")} \
        if os.path.exists(f"{pasta}/bsis.jsonl") else {}
    out = []
    for f in jl("faglflexa"):
        if f["BUZEI"] == "000":
            continue
        b = bkpf[(f["DOCNR"], f["RYEAR"])]
        s = bseg[(f["DOCNR"], f["RYEAR"], f["BUZEI"])]
        texto = s["SGTXT"].split("|")[0].rstrip()
        ref = bsis.get((f["DOCNR"], f["RYEAR"], f["BUZEI"]), b["XBLNR"])
        out.append({
            "Nº doc.": float(int(f["DOCNR"])),
            "Referência": excel_tipado(ref),
            "Div": _como_excel(s["GSBER"]),
            "Tip": b["BLART"],
            "Dt.lçto.": dt.datetime.strptime(b["BUDAT"], "%Y%m%d").date(),
            "CL": _como_excel(s["BSCHL"]),
            "Mont.em MI": num(f["HSL"]),
            "MoedI": "BRL",
            "LNeg": _como_excel(s["GSBER"]),
            "Cen.": _como_excel(s["WERKS"]),
            "Centro cst": f["RCNTR"].lstrip("0"),
            "Material": _como_excel(s["MATNR"].lstrip("0")),
            "Cen.lucro": f["PRCTR"],
            "Texto": excel_tipado(texto),
            "Segmento": f["SEGMENT"],
            "Razão": float(int(f["RACCT"])),
            "_ord": (int(f["DOCNR"]), int(f["RACCT"]), int(f["BUZEI"])),
        })
    out.sort(key=lambda r: r["_ord"])
    return out


def gravar_xlsx(rows, destino):
    """Grava as linhas no layout do Razão exportado do SAP (colunas CAB), como o Excel mostra. Download no portal."""
    from xlsx_rapido import Planilha, gravar
    base = dt.date(1899, 12, 30)
    cel = lambda v: ((v - base).days, 3) if isinstance(v, dt.date) else v
    larguras = [12, 16, 6, 5, 11, 5, 16, 6, 6, 6, 11, 14, 11, 50, 9, 12]
    estilos = [0, 0, 0, 0, 3, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    p = Planilha("Razão", larguras, estilos)
    p.cabecalho = CAB
    p.linhas = ([cel(r[c]) for c in CAB] for r in rows)
    p.n_linhas = len(rows)
    gravar(destino, [p])
