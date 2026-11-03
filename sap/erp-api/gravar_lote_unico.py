"""Grava na ERP (EMP), parte por parte, o lote único montado pelo montar_lote_unico.py, com o MESMO número de lote.

Uso: gravar_lote_unico.py PASTA                 -> ensaio: confere as partes e o estado do lote na ERP, NÃO envia
     gravar_lote_unico.py PASTA --enviar [--ate-parte N]

A API não documenta acrescentar partidas a um lote existente (ERP-API.md). Por isso, a cada parte:
  1. lê o lote na ERP e exige que tenha exatamente o que as partes já confirmadas somam (estado.json da pasta);
  2. envia a parte (nonce pelo conteúdo);
  3. lê de novo e só segue se o lote cresceu exatamente o tamanho da parte (partidas, débito e crédito).
     Cresceu = ACRESCENTOU (ok). Ficou com só a parte = SUBSTITUIU (para). Não mudou = não gravou: se foi conta que
     recusa rateio, tira o rateio dessa conta e reenvia; qualquer outra coisa, para.
Erro de conexão/timeout não quer dizer que não gravou: sempre lê antes de decidir. Nunca repete no escuro.
Parte confirmada = documentos marcados como importados no banco do portal (robo_banco.py), se DATABASE_URL existir.
"""
import argparse
import hashlib
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, ".."))
import erp  # noqa: E402

ORG = "EMP"
LOTES_LIBERADOS = {1000001}          # decisão de 16/10/2026: outubro/2026 inteiro no lote 1000001
LISTA = os.path.join(AQUI, "contas_sem_rateio.json")


def estado_erp(lote):
    cab = erp.ler(ORG, "accountingLot", f"fiscalYear EQ 2026 AND accountingLotNumber EQ {lote}",
                   "accountingLotNumber,accountingLotDate,accountingLotType,accountingLotDescription", size=5)
    if not cab.get("content"):
        return None
    ps = erp.ler_todas(ORG, "accountingEntry", f"fiscalYear EQ 2026 AND accountingLotNumberID EQ {lote}",
                        erp.CAMPOS_PARTIDA)
    return {"cab": cab["content"][0], "partidas": len(ps),
            "debito": round(sum(p["amount"] for p in ps if p["type"] == "D"), 2),
            "credito": round(sum(p["amount"] for p in ps if p["type"] == "C"), 2),
            "lancamentos": len({p["number"] for p in ps})}


def igual(r, n, d, c):
    return r["partidas"] == n and abs(r["debito"] - d) < 0.005 and abs(r["credito"] - c) < 0.005


def conferir_parte(corpo, lote):
    p = corpo["payload"]
    assert p["accountingLotNumber"] == lote, "parte de outro lote"
    es = p["accountingEntry"]
    assert es, "parte sem partidas"
    saldo = {}
    for e in es:
        assert e["type"] in ("D", "C") and isinstance(e["account"], int) and e["amount"] > 0, e
        assert e["date"].startswith("2026-") and e["branch"] == 1 and len(e.get("description", "")) <= 70, e
        saldo[e["number"]] = saldo.get(e["number"], 0) + (e["amount"] if e["type"] == "D" else -e["amount"])
    assert all(abs(v) < 0.005 for v in saldo.values()), "lançamento com D≠C"
    deb = round(sum(e["amount"] for e in es if e["type"] == "D"), 2)
    cre = round(sum(e["amount"] for e in es if e["type"] == "C"), 2)
    assert abs(deb - cre) < 0.005, f"parte com D≠C: {deb} x {cre}"
    return len(es), deb


def sem_rateio():
    return set(json.load(open(LISTA))) if os.path.exists(LISTA) else set()


def tirar_rateio(corpo, contas):
    n = 0
    for e in corpo["payload"]["accountingEntry"]:
        if e["account"] in contas and e.pop("costCenters", None) is not None:
            n += 1
    return n


def marcar_importado(pasta, nome, lote):
    if not os.environ.get("DATABASE_URL"):
        return "DATABASE_URL ausente: documentos NÃO marcados no banco do portal"
    import robo_banco
    return robo_banco.importado(pasta, lote, os.path.join(pasta, f"{nome}.docs.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--enviar", action="store_true")
    ap.add_argument("--ate-parte", type=int, default=10 ** 6)
    a = ap.parse_args()
    resumo = json.load(open(os.path.join(a.pasta, "resumo.json")))
    lote = resumo["lote"]
    if lote not in LOTES_LIBERADOS:
        sys.exit(f"PARADO: lote {lote} não liberado para o lote único")
    caminho_estado = os.path.join(a.pasta, "estado.json")
    est = json.load(open(caminho_estado)) if os.path.exists(caminho_estado) else {"lote": lote, "confirmadas": []}
    assert est["lote"] == lote

    partes = sorted(f[:-5] for f in os.listdir(a.pasta) if f.startswith("parte_") and f.endswith(".json")
                    and not f.endswith(".docs.json") and not f.endswith(".lido.json"))
    contas = sem_rateio()
    total_n = total_d = 0.0
    for nome in partes:
        n, d = conferir_parte(json.load(open(os.path.join(a.pasta, f"{nome}.json"))), lote)
        total_n += n
        total_d += d
    print(f"lote {lote}: {len(partes)} partes, {int(total_n)} partidas, D=C {total_d:,.2f}; "
          f"já confirmadas: {len(est['confirmadas'])}", flush=True)

    for nome in partes:
        if nome in {c["parte"] for c in est["confirmadas"]}:
            continue
        if int(nome.split("_")[1]) > a.ate_parte:
            print(f"parado antes da {nome} (--ate-parte {a.ate_parte})")
            return
        exp_n = sum(c["partidas"] for c in est["confirmadas"])
        exp_d = round(sum(c["debito"] for c in est["confirmadas"]), 2)
        antes = estado_erp(lote)
        if exp_n == 0:
            if antes is not None:
                sys.exit(f"PARADO: o lote {lote} já existe na ERP e nenhuma parte foi confirmada por aqui: {antes}")
        elif antes is None or not igual(antes, exp_n, exp_d, exp_d):
            sys.exit(f"PARADO antes da {nome}: a ERP tem {antes}, esperado {exp_n} partidas / D=C {exp_d:,.2f}")
        corpo = json.load(open(os.path.join(a.pasta, f"{nome}.json")))
        k = tirar_rateio(corpo, contas)
        n, d = conferir_parte(corpo, lote)
        print(f"\n=== {nome}: {n} partidas, D=C {d:,.2f} (rateio tirado de {k}) | ERP antes: "
              f"{antes['partidas'] if antes else 'lote não existe'}", flush=True)
        if not a.enviar:
            continue
        for _tentativa in range(40):
            bruto = json.dumps(corpo, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            assert len(bruto) <= erp.MAX_BYTES, f"{nome} com {len(bruto)} bytes"
            nonce = f"contabil-{ORG}-{lote}-{hashlib.sha256(bruto).hexdigest()[:40]}"
            try:
                st, txt = erp._req("POST", "insert", {"organization": ORG, "entity": "accountingLot", "nonce": nonce},
                                    bruto, timeout=600)
            except Exception as e:  # noqa: BLE001 — sem resposta: não sabemos se gravou
                st, txt = None, repr(e)
            print(f"insert: HTTP {st} {txt[:300]}", flush=True)
            depois = estado_erp(lote)
            print(f"lido: {depois}", flush=True)
            if depois is not None and igual(depois, exp_n + n, exp_d + d, exp_d + d):
                break
            if depois is not None and exp_n and igual(depois, n, d, d):
                sys.exit(f"PARADO: a {nome} SUBSTITUIU as partidas do lote {lote} (tinha {exp_n}, ficou {n}). "
                         "O insert num lote existente não acrescenta.")
            if (depois is None and exp_n == 0) or (depois is not None and igual(depois, exp_n, exp_d, exp_d)):
                m = erp.RE_SEM_RATEIO.search(txt)
                if not m:
                    sys.exit(f"PARADO na {nome}: não gravou (HTTP {st}). Conferir antes de repetir.")
                conta = int(m.group(1))
                contas.add(conta)
                json.dump(sorted(contas), open(LISTA, "w"))
                k = tirar_rateio(corpo, {conta})
                print(f"--- conta {conta} não aceita rateio: tirado de {k} partida(s); reenviando", flush=True)
                if not k:
                    sys.exit(f"PARADO: conta {conta} recusou rateio mas nenhuma partida tinha rateio")
                continue
            sys.exit(f"PARADO na {nome}: estado inesperado na ERP: {depois} (esperado {exp_n + n} partidas)")
        else:
            sys.exit(f"PARADO na {nome}: tentativas demais")
        json.dump(corpo, open(os.path.join(a.pasta, f"{nome}.json"), "w"), ensure_ascii=False)
        est["confirmadas"].append({"parte": nome, "partidas": n, "debito": d})
        json.dump(est, open(caminho_estado, "w"), indent=1)
        print(f"{nome} CONFERE: lote {lote} com {exp_n + n} partidas | {marcar_importado(a.pasta, nome, lote)}",
              flush=True)
    print(f"\nFIM: {len(est['confirmadas'])} partes confirmadas no lote {lote}.")


if __name__ == "__main__":
    main()
