"""Tabelas de apoio (plano de contas, centros de custo, contas SAP).

Produção: Postgres do Supabase, schema `contabil` (DATABASE_URL, role contabil_app).
Desenvolvimento/testes: CSVs em app/dados/ (quando DATABASE_URL não está definida).
"""
import csv
import json
import os
import threading

import conversor

DEFINICOES = {
    "plano": {
        "tabela": "plano_contas",
        "arquivo": "plano_contas.csv",
        "chave": "conta_sap",
        "campos": ["conta_sap", "conta_erp", "nome_conta", "sintetica_erp", "conta_referencial"],
        "rotulos": ["Conta SAP", "Conta ERP", "Nome da conta", "Sintética ERP", "Conta referencial"],
        "obrigatorios": ["conta_sap", "conta_erp"],
        "numericos": ["conta_sap", "conta_erp"],
    },
    "cc": {
        "tabela": "centro_custo",
        "arquivo": "centro_custo.csv",
        "chave": "centro_custo_sap",
        "campos": ["centro_custo_sap", "centro_custo_resumido", "centro_custo_erp"],
        "rotulos": ["Centro de custo SAP", "Resumido", "Centro de custo ERP"],
        "obrigatorios": ["centro_custo_sap", "centro_custo_erp"],
        "numericos": ["centro_custo_sap", "centro_custo_erp"],
    },
    "contas_sap": {
        "tabela": "contas_sap",
        "arquivo": "contas_sap.csv",
        "chave": "conta_sap",
        "campos": ["conta_sap", "nome_conta_sap"],
        "rotulos": ["Conta SAP", "Nome no SAP"],
        "obrigatorios": ["conta_sap"],
        "numericos": ["conta_sap"],
    },
}

_trava = threading.Lock()
DATABASE_URL = os.environ.get("DATABASE_URL")


def origem():
    return "supabase" if DATABASE_URL else "csv"


def _conectar():
    import psycopg
    # porta 6543 = Supavisor em modo transação: sem prepared statements
    return psycopg.connect(DATABASE_URL, prepare_threshold=None, autocommit=False, connect_timeout=10)


def ler(nome):
    d = DEFINICOES[nome]
    if DATABASE_URL:
        with _conectar() as con:
            cur = con.execute(
                f"select {', '.join(d['campos'])} from contabil.{d['tabela']} order by {d['chave']}"
            )
            return [dict(zip(d["campos"], (v or "" for v in linha))) for linha in cur.fetchall()]
    with open(os.path.join(conversor.DADOS, d["arquivo"]), newline="", encoding="utf-8") as fh:
        return [{c: r.get(c) or "" for c in d["campos"]} for r in csv.DictReader(fh)]


def carregar_para_conversao():
    """Tabelas no formato que conversor.converter espera."""
    return conversor.montar_tabelas(ler("plano"), ler("cc"), ler("contas_sap"))


def aplicar(nome, remover=(), incluir=(), manter_so=None, origem_mudanca="site"):
    """Altera uma tabela numa transação só.

    remover:   chaves cujas linhas saem
    incluir:   linhas novas (substituem as que têm a mesma chave)
    manter_so: {chave: valor da conta ERP} — para duplicadas: mantém só a linha com esse valor
    """
    d = DEFINICOES[nome]
    chave = d["chave"]
    incluir = [{c: (l.get(c) or "").strip() for c in d["campos"]} for l in incluir]
    with _trava:
        if DATABASE_URL:
            with _conectar() as con, con.transaction():
                for k in remover:
                    con.execute(f"delete from contabil.{d['tabela']} where {chave} = %s", (k,))
                for k, valor in (manter_so or {}).items():
                    con.execute(f"delete from contabil.{d['tabela']} where {chave} = %s and conta_erp <> %s", (k, valor))
                for l in incluir:
                    con.execute(f"delete from contabil.{d['tabela']} where {chave} = %s", (l[chave],))
                    con.execute(
                        f"insert into contabil.{d['tabela']} ({', '.join(d['campos'])}) "
                        f"values ({', '.join(['%s'] * len(d['campos']))})",
                        [l[c] for c in d["campos"]],
                    )
                con.execute(
                    "insert into contabil.historico (tabela, origem, dados) values (%s, %s, %s)",
                    (d["tabela"], origem_mudanca, json.dumps(
                        {"remover": list(remover), "incluir": incluir, "manter_so": manter_so or {}},
                        ensure_ascii=False)),
                )
            return
        linhas = ler(nome)
        linhas = [l for l in linhas if conversor._cod(l[chave]) not in set(map(str, remover))]
        for k, valor in (manter_so or {}).items():
            linhas = [l for l in linhas if conversor._cod(l[chave]) != k or conversor._cod(l["conta_erp"]) == valor]
        novas = {l[chave] for l in incluir}
        linhas = [l for l in linhas if conversor._cod(l[chave]) not in novas] + incluir
        linhas.sort(key=lambda l: conversor._cod(l[chave]))
        caminho = os.path.join(conversor.DADOS, d["arquivo"])
        with open(caminho + ".tmp", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=d["campos"])
            w.writeheader()
            w.writerows(linhas)
        os.replace(caminho + ".tmp", caminho)
