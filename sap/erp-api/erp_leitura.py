"""Leitura SOMENTE da ERP API (ERP): só GET em /api/v1/get-list. Não grava, não altera e não exclui nada.

Uso: erp_leitura.py ORG ENTIDADE "BUSCA" [CAMPOS] [--todas] > saida.json
     (ex.: EMP accountingLot "fiscalYear EQ 2026 AND accountingLotNumber GT 900000" "*")
Token em ~/.erp-token-producao (nunca impresso).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.erp.example.com/api/v1/get-list"  # única rota permitida


def _token():
    with open(os.path.expanduser("~/.erp-token-producao")) as f:
        return f.read().strip()


def ler(org, entidade, busca, campos="*", size=1000, page=0, tentativas=4):
    q = urllib.parse.urlencode({"organization": org, "entity": entidade, "search": busca, "fields": campos,
                                "size": size, "page": page})
    req = urllib.request.Request(f"{BASE}?{q}", method="GET", headers={"Authorization": f"Bearer {_token()}"})
    assert req.get_method() == "GET" and req.full_url.startswith(BASE + "?")
    for n in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            corpo = e.read().decode(errors="replace")[:300]
            # 100001 socket / 100006 sem sessão: instabilidade do gateway, esperar e tentar de novo (é só leitura)
            if e.code in (403, 500, 502, 503) and n + 1 < tentativas:
                time.sleep(60)
                continue
            raise SystemExit(f"HTTP {e.code}: {corpo}")


def ler_todas(org, entidade, busca, campos="*", size=1000):
    out, page = [], 0
    while True:
        r = ler(org, entidade, busca, campos, size, page)
        itens = r.get("content") or []
        out.extend(itens)
        print(f"  página {page}: {len(itens)} (total {len(out)})", file=sys.stderr)
        if len(itens) < size:
            return out
        page += 1


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--todas"]
    org, ent, busca = a[:3]
    campos = a[3] if len(a) > 3 else "*"
    if "--todas" in sys.argv:
        json.dump(ler_todas(org, ent, busca, campos), sys.stdout, ensure_ascii=False)
    else:
        json.dump(ler(org, ent, busca, campos, size=200), sys.stdout, ensure_ascii=False)
