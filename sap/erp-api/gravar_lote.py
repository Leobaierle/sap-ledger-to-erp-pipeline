"""Grava UM lote contábil na ERP pela ERP API (EMP) e confere pela leitura.

Uso: gravar_lote.py LOTE.json             -> ensaio: confere tudo e NÃO envia
     gravar_lote.py LOTE.json --enviar    -> envia, lê de volta e confere

Travas (qualquer uma falhando = não envia):
  - empresa EMP; número do lote entre 1000006 e 1099999 (outubro/2026 em diante, decisão de 15/10/2026)
  - lote ainda não existe na ERP (consulta antes)
  - débito = crédito no lote e em cada lançamento; contas inteiras; datas dentro de 2026; filial 1
  - nonce fixo pelo conteúdo: o ERP recusa a mesma requisição duas vezes
Erro de conexão NÃO quer dizer que não gravou: o script lê o lote antes de qualquer nova tentativa e nunca repete
sozinho. Token em ~/.erp-token-producao (nunca impresso).
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_leitura  # noqa: E402

ORG = "EMP"
LOTE_MIN, LOTE_MAX = 1000006, 1099999
BASE = "https://api.erp.example.com/api/v1"
MAX_BYTES = 950_000      # 15/10/2026: 2,8 MB voltou HTTP 413 do nginx da api.erp.example.com
CAMPOS = "number,sequential,date,account,branch.branch,document,amount,type,entryObservation.description"


def conferir_corpo(corpo):
    p = corpo["payload"]
    lote = p["accountingLotNumber"]
    assert isinstance(lote, int) and LOTE_MIN <= lote <= LOTE_MAX, f"lote fora da faixa liberada: {lote}"
    es = p["accountingEntry"]
    assert es, "lote sem partidas"
    saldo = defaultdict(float)
    for e in es:
        assert e["type"] in ("D", "C") and isinstance(e["account"], int) and e["amount"] > 0, e
        assert e["date"].startswith("2026-") and e["branch"] == 1, e
        assert len(e.get("description", "")) <= 70, e
        saldo[e["number"]] += e["amount"] if e["type"] == "D" else -e["amount"]
    ruins = {k: round(v, 2) for k, v in saldo.items() if abs(v) > 0.005}
    assert not ruins, f"lançamentos com D≠C: {list(ruins.items())[:5]}"
    deb = round(sum(e["amount"] for e in es if e["type"] == "D"), 2)
    cre = round(sum(e["amount"] for e in es if e["type"] == "C"), 2)
    assert abs(deb - cre) < 0.005, f"lote com D≠C: {deb} x {cre}"
    return lote, len(es), deb


def ler_lote(lote):
    cab = erp_leitura.ler(ORG, "accountingLot", f"fiscalYear EQ 2026 AND accountingLotNumber EQ {lote}",
                            "accountingLotNumber,accountingLotDate,accountingLotType,accountingLotDescription",
                            size=5, tentativas=1)
    return cab.get("content") or []


def ler_partidas(lote):
    return erp_leitura.ler_todas(ORG, "accountingEntry",
                                   f"fiscalYear EQ 2026 AND accountingLotNumberID EQ {lote}", CAMPOS)


def main():
    caminho = sys.argv[1]
    enviar = "--enviar" in sys.argv[2:]
    corpo = json.load(open(caminho))
    lote, n, deb = conferir_corpo(corpo)
    bruto = json.dumps(corpo, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert len(bruto) <= MAX_BYTES, f"corpo com {len(bruto)} bytes; o nginx da ERP recusa acima de ~1 MB (HTTP 413)"
    nonce = f"contabil-{ORG}-{lote}-{hashlib.sha256(bruto).hexdigest()[:40]}"
    print(f"lote {lote}: {n} partidas, D=C R$ {deb:,.2f}, {len(bruto) / 1e6:.1f} MB, nonce {nonce}")

    existente = ler_lote(lote)
    if existente:
        sys.exit(f"PARADO: o lote {lote} já existe na ERP: {existente}")
    print("lote não existe na ERP: ok")
    if not enviar:
        print("ENSAIO: nada enviado (use --enviar para gravar)")
        return

    q = urllib.parse.urlencode({"organization": ORG, "entity": "accountingLot", "nonce": nonce})
    req = urllib.request.Request(f"{BASE}/insert?{q}", data=bruto, method="POST", headers={
        "Authorization": f"Bearer {erp_leitura._token()}", "Content-Type": "application/json",
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            print(f"insert: HTTP {r.status} {r.read().decode(errors='replace')[:300]}")
    except urllib.error.HTTPError as e:
        print(f"insert: HTTP {e.code} {e.read().decode(errors='replace')[:400]}")
    except Exception as e:  # noqa: BLE001 — timeout/conexão: não sabemos se gravou
        print(f"insert: sem resposta ({e!r})")

    # confere sempre pela leitura, gravando ou não
    cab = ler_lote(lote)
    if not cab:
        sys.exit(f"VERIFICAR: o lote {lote} não aparece na leitura. NÃO repetir sem conferir na ERP.")
    ps = ler_partidas(lote)
    d = round(sum(p["amount"] for p in ps if p["type"] == "D"), 2)
    c = round(sum(p["amount"] for p in ps if p["type"] == "C"), 2)
    ok = len(ps) == n and abs(d - deb) < 0.005 and abs(c - deb) < 0.005
    print(f"lido de volta: {cab[0]} | {len(ps)} partidas, D {d:,.2f} C {c:,.2f} -> {'CONFERE' if ok else 'NÃO CONFERE'}")
    json.dump(ps, open(caminho.replace(".json", ".lido.json"), "w"), ensure_ascii=False)
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
