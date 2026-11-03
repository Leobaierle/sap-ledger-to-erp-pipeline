"""Balancete do SAP (empresa 1200, ledger 0L) a partir de faglflext.jsonl + skat.jsonl, lidos na mesma extração do
Razão. Mesma base do RFBILA00 (Estrutura de balanço) que a contabilidade cola na planilha MÊS: saldo acumulado por
conta = saldo de abertura (HSLVT) + movimento dos períodos até o mês. Débito/crédito do mês pelo DRCRK (S/H).
Valores com sinal do SAP no saldo (+ devedor, − credor); débito e crédito do mês positivos.

Uso: montar_balancete.py PASTA_EXTRACAO AAAAMM DESTINO.xlsx"""
import json
import os
import sys
import datetime as dt
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from montar_razao import num

CAB_CONTA = ["Conta", "Nome da conta", "Saldo anterior", "Débito", "Crédito", "Saldo atual"]


def balancete(pasta, ano, mes):
    """{(divisão, conta): [saldo anterior, débito, crédito, saldo atual]} do mês."""
    b = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for l in open(f"{pasta}/faglflext.jsonl"):
        x = json.loads(l)
        if int(x["RYEAR"]) != ano:
            continue
        v = b[(x["RBUSA"], x["RACCT"])]
        v[0] += num(x["HSLVT"]) + sum(num(x[f"HSL{m:02d}"]) for m in range(1, mes))
        m = num(x[f"HSL{mes:02d}"])
        if x["DRCRK"] == "S":
            v[1] += m
        else:
            v[2] -= m
    for v in b.values():
        v[3] = v[0] + v[1] - v[2]
    return {k: [round(x, 2) for x in v] for k, v in b.items() if any(abs(x) >= 0.005 for x in v)}


def nomes(pasta):
    return {x["SAKNR"]: x["TXT50"] for x in map(json.loads, open(f"{pasta}/skat.jsonl"))}


def conferir(pasta, ano, mes):
    """Contas cujo movimento do mês no balancete difere do Razão extraído (FAGLFLEXA): lançamento feito durante a
    extração. Devolve [(conta, balancete, razão)]."""
    bkpf = {(x["BELNR"], x["GJAHR"]): x["BUDAT"] for x in map(json.loads, open(f"{pasta}/bkpf.jsonl"))}
    raz = defaultdict(float)
    for x in map(json.loads, open(f"{pasta}/faglflexa.jsonl")):
        if bkpf[(x["DOCNR"], x["RYEAR"])][:6] == f"{ano}{mes:02d}":
            raz[x["RACCT"]] += num(x["HSL"])
    bal = defaultdict(float)
    for (_div, conta), v in balancete(pasta, ano, mes).items():
        bal[conta] += v[1] - v[2]
    return [(c, round(bal[c], 2), round(raz[c], 2)) for c in sorted(set(bal) | set(raz)) if abs(bal[c] - raz[c]) >= 0.005]


def gravar_xlsx(pasta, meses, destino):
    """Uma aba por conta e uma por divisão para cada mês (ano, mês) da janela."""
    from xlsx_rapido import Planilha, gravar
    nome = nomes(pasta)
    conta = lambda c: float(int(c)) if c.isdigit() else c
    abas = []
    for ano, mes in meses:
        b = balancete(pasta, ano, mes)
        por_conta = defaultdict(lambda: [0.0] * 4)
        for (_div, c), v in b.items():
            por_conta[c] = [a + x for a, x in zip(por_conta[c], v)]
        p = Planilha(f"Balancete {mes:02d}.{ano}", [13, 50, 18, 18, 18, 18], [0, 5, 4, 4, 4, 4])
        p.cabecalho = CAB_CONTA
        p.linhas = [[conta(c), nome.get(c, "")] + [round(x, 2) for x in v] for c, v in sorted(por_conta.items())
                    if any(abs(x) >= 0.005 for x in v)]
        p.n_linhas = len(p.linhas)
        d = Planilha(f"Por divisão {mes:02d}.{ano}", [9, 13, 50, 18, 18, 18, 18], [0, 0, 5, 4, 4, 4, 4])
        d.cabecalho = ["Divisão"] + CAB_CONTA
        d.linhas = [[conta(div), conta(c), nome.get(c, "")] + v for (div, c), v in sorted(b.items())]
        d.n_linhas = len(d.linhas)
        abas += [p, d]
    gravar(destino, abas)


if __name__ == "__main__":
    pasta, aaaamm, destino = sys.argv[1:4]
    ano, mes = int(aaaamm[:4]), int(aaaamm[4:])
    gravar_xlsx(pasta, [(ano, mes)], destino)
    dif = conferir(pasta, ano, mes)
    print(destino, "| contas com movimento diferente do Razão:", len(dif), dif[:10])
