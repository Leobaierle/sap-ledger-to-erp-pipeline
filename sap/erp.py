"""Cliente da ERP API (ERP) para o robô: ler, gravar UM lote com travas e conferir pela leitura.

Token: variável ERP_TOKEN ou ~/.erp-token-producao. Nunca impresso.
Regras aprendidas em 15/10/2026 (ERP-API.md):
- corpo acima de ~1 MB = HTTP 413 do nginx; a API corta em 60 s (ERP grava ~70 ms/partida);
- conta "configurada para não informar rateio de centro de custo" recusa o lote inteiro (nada gravado): tira o rateio
  dessa conta, anota e reenvia;
- erro de conexão/timeout NÃO quer dizer que não gravou: sempre ler antes de qualquer nova tentativa;
- get-list sempre com campos nomeados (fields=* em accountingLot derrubou o serviço).
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.erp.example.com/api/v1"
LOTE_MIN, LOTE_MAX = 1000006, 1099999
MAX_BYTES = 950_000
CAMPOS_PARTIDA = "number,sequential,date,account,branch.branch,document,amount,type,entryObservation.description"
RE_SEM_RATEIO = re.compile(r"A conta [\d.]*?(\d+) .*?configurada para não informar rateio de centro de custo")


class ErroErp(Exception):
    pass


def _token():
    t = os.environ.get("ERP_TOKEN")
    if not t:
        with open(os.path.expanduser("~/.erp-token-producao")) as f:
            t = f.read()
    return t.strip()


def _req(metodo, rota, params, corpo=None, timeout=180):
    url = f"{BASE}/{rota}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, data=corpo, method=metodo, headers={
        "Authorization": f"Bearer {_token()}", "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def ler(org, entidade, busca, campos, size=1000, page=0, tentativas=4):
    assert campos and campos != "*" and "*" not in campos, "nomear os campos"
    for n in range(tentativas):
        st, txt = _req("GET", "get-list", {"organization": org, "entity": entidade, "search": busca, "fields": campos,
                                            "size": size, "page": page})
        if st == 200:
            return json.loads(txt)
        if st in (403, 500, 502, 503) and n + 1 < tentativas:
            time.sleep(30)
            continue
        raise ErroErp(f"leitura {entidade}: HTTP {st} {txt[:300]}")


def ler_todas(org, entidade, busca, campos, size=1000):
    out, page = [], 0
    while True:
        itens = ler(org, entidade, busca, campos, size, page).get("content") or []
        out += itens
        if len(itens) < size:
            return out
        page += 1


def lotes_existentes(org, de=LOTE_MIN, ate=LOTE_MAX, ano=2026):
    r = ler_todas(org, "accountingLot", f"fiscalYear EQ {ano} AND accountingLotNumber GT {de - 1} AND "
                                        f"accountingLotNumber LT {ate + 1}", "accountingLotNumber")
    return {x["accountingLotNumber"] for x in r}


def _conferir_corpo(corpo):
    p = corpo["payload"]
    lote, es = p["accountingLotNumber"], p["accountingEntry"]
    if not (isinstance(lote, int) and LOTE_MIN <= lote <= LOTE_MAX):
        raise ErroErp(f"lote fora da faixa liberada: {lote}")
    if not es:
        raise ErroErp("lote sem partidas")
    saldo = {}
    for e in es:
        if e["type"] not in ("D", "C") or not isinstance(e["account"], int) or e["amount"] <= 0 or e["branch"] != 1 \
                or len(e.get("description", "")) > 70:
            raise ErroErp(f"partida inválida: {e}")
        saldo[e["number"]] = saldo.get(e["number"], 0) + (e["amount"] if e["type"] == "D" else -e["amount"])
    if any(abs(v) > 0.005 for v in saldo.values()):
        raise ErroErp("lançamento com D≠C")
    deb = round(sum(e["amount"] for e in es if e["type"] == "D"), 2)
    cre = round(sum(e["amount"] for e in es if e["type"] == "C"), 2)
    if abs(deb - cre) > 0.005:
        raise ErroErp(f"lote com D≠C: {deb} x {cre}")
    return lote, len(es), deb


def conferir_lote(org, lote, n, deb):
    cab = ler(org, "accountingLot", f"fiscalYear EQ 2026 AND accountingLotNumber EQ {lote}",
              "accountingLotNumber,accountingLotDate,accountingLotType,accountingLotDescription", size=5)
    if not cab.get("content"):
        return None
    ps = ler_todas(org, "accountingEntry", f"fiscalYear EQ 2026 AND accountingLotNumberID EQ {lote}", CAMPOS_PARTIDA)
    d = round(sum(p["amount"] for p in ps if p["type"] == "D"), 2)
    c = round(sum(p["amount"] for p in ps if p["type"] == "C"), 2)
    return {"partidas": len(ps), "debito": d, "credito": c,
            "confere": len(ps) == n and abs(d - deb) < 0.005 and abs(c - deb) < 0.005}


def gravar(org, corpo, sem_rateio_novo=None, log=print):
    """Grava UM lote e confere. sem_rateio_novo(conta) é chamado para cada conta que recusar rateio.
    Devolve o resultado da conferência; levanta ErroErp em qualquer outra situação (sem repetir no escuro)."""
    if org != "EMP":
        raise ErroErp(f"empresa não permitida: {org}")
    for _ in range(80):
        lote, n, deb = _conferir_corpo(corpo)
        bruto = json.dumps(corpo, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        if len(bruto) > MAX_BYTES:
            raise ErroErp(f"lote {lote} com {len(bruto)} bytes (limite ~1 MB)")
        if conferir_lote(org, lote, n, deb) is not None:
            raise ErroErp(f"o lote {lote} já existe na ERP")
        nonce = f"contabil-{org}-{lote}-{hashlib.sha256(bruto).hexdigest()[:40]}"
        st, txt = _req("POST", "insert", {"organization": org, "entity": "accountingLot", "nonce": nonce}, bruto,
                       timeout=600)
        log(f"lote {lote}: {n} partidas, R$ {deb:,.2f} -> HTTP {st} {txt[:200]}")
        conf = conferir_lote(org, lote, n, deb)
        if conf is not None:
            if not conf["confere"]:
                raise ErroErp(f"lote {lote} gravado mas NÃO confere: {conf}")
            return {"lote": lote, **conf}
        m = RE_SEM_RATEIO.search(txt)
        if st == 200 or not m:
            raise ErroErp(f"lote {lote} não aparece na leitura depois de HTTP {st}: {txt[:300]}. Conferir na ERP "
                           "antes de tentar de novo.")
        conta = int(m.group(1))
        if sem_rateio_novo:
            sem_rateio_novo(conta)
        k = 0
        for e in corpo["payload"]["accountingEntry"]:
            if e["account"] == conta and e.pop("costCenters", None) is not None:
                k += 1
        log(f"conta {conta} não aceita rateio: tirado de {k} partida(s); reenviando")
        if not k:
            raise ErroErp(f"conta {conta} recusou rateio mas nenhuma partida tinha rateio")
    raise ErroErp("tentativas demais")
