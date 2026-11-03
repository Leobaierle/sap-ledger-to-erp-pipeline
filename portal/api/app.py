"""API do portal do robô diário da ACME (SAP -> conversão -> ERP).

Lê o estado que o robô grava no schema `contabil` (tabelas robo_*, ver portal/sql/) e reaproveita o
`app/tabelas.py` do conversor para o plano de contas e os centros de custo (mesmas tabelas e histórico).
"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import time
from decimal import Decimal
from urllib.parse import unquote

from flask import Flask, abort, g, request, send_file, send_from_directory

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "..", "app"))
import tabelas  # noqa: E402  (precisa do DATABASE_URL já no ambiente)

WEB = os.environ.get("PORTAL_WEB", os.path.join(AQUI, "..", "web", "dist"))
ARQUIVOS = os.path.realpath(os.environ.get("PORTAL_ARQUIVOS", os.path.join(AQUI, "..", "arquivos")))
ETAPAS = ["Extração SAP", "Conversão", "Envio p/ ERP", "Importação ERP"]

# Login: o mesmo dos consoles internos (portal.example.com). O console-gateway faz o login pela
# Microsoft e grava o cookie `auth_token` ("Bearer <JWT HS256>") no domínio portal.example.com; aqui só
# se confere a assinatura com o mesmo JWT_SECRET e a plataforma. Sem JWT_SECRET a API fica fechada, a não ser
# com PORTAL_SEM_LOGIN=1 (só desenvolvimento local).
JWT_SECRET = os.environ.get("JWT_SECRET", "").encode()
SEM_LOGIN = os.environ.get("PORTAL_SEM_LOGIN") == "1"
PLATAFORMA = os.environ.get("PORTAL_PLATAFORMA", "contabilidade")
GATEWAY = os.environ.get("AUTH_GATEWAY", "https://api.example.com").rstrip("/")

app = Flask(__name__, static_folder=None)


class ErroApi(Exception):
    def __init__(self, mensagem, status=400):
        super().__init__(mensagem)
        self.status = status


@app.errorhandler(ErroApi)
def _erro_api(e):
    return {"erro": str(e)}, e.status


def _b64(parte):
    return base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4))


def _sessao():
    """Payload do cookie auth_token, ou None se faltar, estiver vencido ou com assinatura errada."""
    # o gateway (hono) grava o cookie com encodeURIComponent: "Bearer%20<jwt>"
    bruto = unquote(request.cookies.get("auth_token") or "") or request.headers.get("Authorization") or ""
    token = bruto.split()[-1] if bruto.split() else ""
    try:
        cab, corpo, assinatura = token.split(".")
        if json.loads(_b64(cab)).get("alg") != "HS256":
            return None
        esperado = hmac.new(JWT_SECRET, f"{cab}.{corpo}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(esperado, _b64(assinatura)):
            return None
        p = json.loads(_b64(corpo))
    except (ValueError, TypeError):
        return None
    if not p.get("sub") or (p.get("exp") is not None and p["exp"] < time.time()):
        return None
    return p


def _tem_acesso(p):
    return p.get("role") == "admin" or PLATAFORMA in (p.get("platforms") or [])


@app.before_request
def _exigir_login():
    if not request.path.startswith("/api/") or request.path == "/api/me":
        return None
    if SEM_LOGIN:
        g.usuario = "dev"
        return None
    if not JWT_SECRET:
        return {"erro": "Login não configurado (JWT_SECRET)."}, 503
    p = _sessao()
    if not p:
        return {"erro": "Sessão expirada. Entre de novo."}, 401
    if not _tem_acesso(p):
        return {"erro": "Sua conta não tem acesso a este portal."}, 403
    g.usuario = p.get("email") or p["sub"]
    return None


def _origem():
    """Quem mudou as tabelas de apoio (vai para contabil.historico)."""
    return f"portal:{g.get('usuario', '')}"


@app.get("/api/me")
def api_me():
    if SEM_LOGIN:
        return {"usuario": {"email": "dev"}, "acesso": True, "gateway": GATEWAY, "sem_login": True}
    p = _sessao() if JWT_SECRET else None
    if not p:
        return {"usuario": None, "acesso": False, "gateway": GATEWAY}
    return {"usuario": {"email": p.get("email"), "role": p.get("role")}, "acesso": _tem_acesso(p),
            "plataforma": PLATAFORMA, "gateway": GATEWAY}


def _con():
    if not tabelas.DATABASE_URL:
        raise ErroApi("Banco não configurado (DATABASE_URL).", 503)
    return tabelas._conectar()


def _json(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, dt.datetime):
        return v.isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    return v


def _linhas(cur):
    nomes = [c.name for c in cur.description]
    return [{n: _json(v) for n, v in zip(nomes, r)} for r in cur.fetchall()]


def _config(con):
    return {k: v for k, v in con.execute("select chave, valor from contabil.robo_config").fetchall()}


def _codigo_livre():
    codigos = [int(r["conta_erp"]) for r in tabelas.ler("plano") if str(r["conta_erp"]).isdigit()]
    return (max(codigos) if codigos else 0) + 1


def _etapas(con, ids):
    if not ids:
        return {}
    cur = con.execute("select execucao_id, n, status, iniciado_em, terminado_em, nota from contabil.robo_etapa "
                      "where execucao_id = any(%s) order by execucao_id, n", (ids,))
    out = {}
    for e in _linhas(cur):
        e["nome"] = ETAPAS[e["n"] - 1]
        out.setdefault(e.pop("execucao_id"), []).append(e)
    return out


COLS_EXEC = ("id, data, sigla, status, periodo_de, periodo_ate, iniciado_em, terminado_em, docs_extraidos, docs_novos, "
             "docs_segurados, lancamentos, linhas, partes, debito, credito, lote, avisos, conferencia, conferencia_em, "
             "arquivo_planilha is not null as tem_planilha, arquivo_razao is not null as tem_razao, "
             "arquivo_balancete is not null as tem_balancete, observacao")


def _pendencias(con, sigla):
    """Pendências da última conversão que ainda não foram resolvidas nas tabelas de apoio."""
    plano = {r["conta_sap"]: r for r in tabelas.ler("plano")}
    nomes_sap = {r["conta_sap"]: r["nome_conta_sap"] for r in tabelas.ler("contas_sap")}
    # só contas: CC sem de-para não é pendência, sai 0 como na planilha manual (16/10/2026)
    cur = con.execute("select codigo_sap, nome_sap, docs, linhas, debito, credito, historico_exemplo, atualizado_em "
                      "from contabil.robo_pendencia where sigla = %s and tipo = 'conta' order by codigo_sap", (sigla,))
    contas = []
    for p in _linhas(cur):
        r = plano.get(p["codigo_sap"])
        p["salvo"] = {"codigo": r["conta_erp"], "nome": r["nome_conta"]} if r else None
        contas.append(p)
    cur = con.execute("select doc, ano, data_lancamento, valor, contas_sap, desde, liberado_em from contabil.robo_segurado "
                      "where sigla = %s and liberado_em is null order by data_lancamento, doc", (sigla,))
    segurados = _linhas(cur)
    nomes = {**nomes_sap, **{p["codigo_sap"]: p["nome_sap"] for p in contas if p["nome_sap"]}}
    for s in segurados:
        s["liberado"] = all(c in plano for c in s["contas_sap"])
        s["contas"] = [{"conta": c, "nome": nomes.get(c, "")} for c in s["contas_sap"]]
    return {"contas": contas, "segurados": segurados}


@app.get("/health")
def health():
    return {"ok": True, "banco": bool(tabelas.DATABASE_URL)}


@app.get("/api/resumo")
def api_resumo():
    """Tudo que o Painel e a navegação precisam numa chamada."""
    with _con() as con:
        cfg = _config(con)
        sigla = cfg.get("ambiente") or "EMP"
        execs = _linhas(con.execute(f"select {COLS_EXEC} from contabil.robo_execucao order by data desc, id desc limit 62"))
        ultima = execs[0] if execs else None
        if ultima:
            ultima["etapas"] = _etapas(con, [ultima["id"]]).get(ultima["id"], [])
        pend = _pendencias(con, sigla)
        alterados = con.execute("select count(*) from contabil.robo_alteracao where sigla = %s", (sigla,)).fetchone()[0]
        pedido = _pedido(con, sigla)
    hoje = _hoje()
    mes = [e for e in execs if e["data"][:7] == hoje.strftime("%Y-%m")]
    return {
        "config": {"ambiente": sigla, "horario": cfg.get("horario")},
        "hoje": hoje.isoformat(),
        "ultima": ultima,
        "mes": [{"id": e["id"], "data": e["data"], "status": e["status"], "docs_novos": e["docs_novos"],
                 "lancamentos": e["lancamentos"], "lote": e["lote"]} for e in mes],
        "pendencias": {
            "contas": sum(1 for p in pend["contas"] if not p["salvo"]),
            "segurados": sum(1 for s in pend["segurados"] if not s["liberado"]),
        },
        "verificar": [{"id": e["id"], "data": e["data"], "lote": e["lote"]}
                      for e in execs if e["status"] == "verificar" and not e["conferencia"]],
        "alterados": alterados,
        "pedido": pedido,
    }


def _hoje():
    """Data de hoje em Brasília (o pod está em UTC: depois das 21h o date.today() já é amanhã)."""
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date()


def _pedido(con, sigla):
    """Pedido do botão "Executar agora": o aberto (fila/rodando) ou o último terminado há menos de 30 min."""
    p = _linhas(con.execute(
        "select id, pedido_por, criado_em, status, iniciado_em, terminado_em, execucao_id, mensagem, de, ate "
        "from contabil.robo_pedido where sigla = %s and (status in ('fila', 'rodando') "
        "or terminado_em > now() - interval '30 minutes') order by id desc limit 1", (sigla,)))
    return p[0] if p else None


@app.post("/api/executar")
def api_executar():
    """Botão "Executar agora": grava o pedido com o período escolhido (uma competência, de/até, até hoje); o servidor do robô
    (sap/atender_pedido.py) começa em até 1 minuto."""
    b = request.get_json(silent=True) or {}
    try:
        de, ate = dt.date.fromisoformat(b.get("de") or ""), dt.date.fromisoformat(b.get("ate") or "")
    except ValueError:
        raise ErroApi("Informe a competência e o período (de/até).", 400)
    hoje = _hoje()
    if (de.year, de.month) != (ate.year, ate.month):
        raise ErroApi("O período tem que ser de uma competência só.", 400)
    if de > ate:
        raise ErroApi("A data inicial é depois da final.", 400)
    if ate > hoje:
        raise ErroApi("A data final não pode ser depois de hoje.", 400)
    with _con() as con, con.transaction():
        sigla = _config(con).get("ambiente") or "EMP"
        aberto = con.execute("select status from contabil.robo_pedido where sigla = %s and status in ('fila', 'rodando')",
                             (sigla,)).fetchone()
        andamento = con.execute("select 1 from contabil.robo_execucao where sigla = %s and status = 'andamento' "
                                "and iniciado_em > now() - interval '3 hours'", (sigla,)).fetchone()
        if aberto or andamento:
            raise ErroApi("Já existe uma execução pedida ou em andamento. Espere ela terminar.", 409)
        novo = con.execute("insert into contabil.robo_pedido (sigla, pedido_por, de, ate) values (%s, %s, %s, %s) "
                           "on conflict (sigla) where status in ('fila', 'rodando') do nothing",
                           (sigla, g.get("usuario", ""), de, ate)).rowcount
        if not novo:                                     # dois cliques ao mesmo tempo: o índice único segura
            raise ErroApi("Já existe uma execução pedida ou em andamento. Espere ela terminar.", 409)
        return {"pedido": _pedido(con, sigla)}


@app.get("/api/execucoes")
def api_execucoes():
    mes = request.args.get("mes") or ""
    status = request.args.get("status") or ""
    sql, args = f"select {COLS_EXEC} from contabil.robo_execucao where true", []
    if mes and mes != "all":
        sql += " and to_char(data, 'YYYY-MM') = %s"
        args.append(mes)
    if status and status != "all":
        sql += " and status = %s"
        args.append(status)
    with _con() as con:
        execs = _linhas(con.execute(sql + " order by data desc, id desc", args))
        meses = [r[0] for r in con.execute(
            "select distinct to_char(data, 'YYYY-MM') m from contabil.robo_execucao order by m desc").fetchall()]
    return {"execucoes": execs, "meses": meses}


@app.get("/api/execucoes/<int:id_exec>")
def api_execucao(id_exec):
    with _con() as con:
        e = _linhas(con.execute(f"select {COLS_EXEC} from contabil.robo_execucao where id = %s", (id_exec,)))
        if not e:
            abort(404)
        e = e[0]
        e["etapas"] = _etapas(con, [id_exec]).get(id_exec, [])
        e["log"] = _linhas(con.execute("select quando, nivel, etapa, mensagem from contabil.robo_log "
                                       "where execucao_id = %s order by quando, id", (id_exec,)))
        e["prints"] = _linhas(con.execute("select id, quando, arquivo, legenda from contabil.robo_print "
                                          "where execucao_id = %s order by quando", (id_exec,)))
    for p in e["prints"]:
        p["arquivo"] = os.path.basename(p["arquivo"])
    return e


@app.post("/api/execucoes/<int:id_exec>/conferencia")
def api_conferencia(id_exec):
    """Conferência humana de um lote em 'verificar': gravou | nao | null (desfaz)."""
    resultado = (request.get_json(silent=True) or {}).get("resultado")
    if resultado not in ("gravou", "nao", None):
        raise ErroApi("Resultado inválido.")
    with _con() as con, con.transaction():
        st = con.execute("select status from contabil.robo_execucao where id = %s", (id_exec,)).fetchone()
        if not st:
            abort(404)
        if st[0] != "verificar":
            raise ErroApi("Só execuções em 'Verificar' recebem conferência.")
        con.execute("update contabil.robo_execucao set conferencia = %s, conferencia_em = case when %s is null "
                    "then null else now() end where id = %s", (resultado, resultado, id_exec))
    return {"ok": True}


def _arquivo(caminho):
    real = os.path.realpath(os.path.join(ARQUIVOS, caminho))
    if not real.startswith(ARQUIVOS + os.sep) or not os.path.isfile(real):
        raise ErroApi("Arquivo não encontrado.", 404)
    return real


@app.get("/api/execucoes/<int:id_exec>/arquivo/<tipo>")
def api_execucao_arquivo(id_exec, tipo):
    if tipo not in ("planilha", "razao", "balancete"):
        abort(404)
    with _con() as con:
        r = con.execute(f"select arquivo_{tipo} from contabil.robo_execucao where id = %s", (id_exec,)).fetchone()
    if not r or not r[0]:
        raise ErroApi("Esta execução não tem esse arquivo.", 404)
    if r[0].startswith("s3://"):                     # Razão e planilha do robô ficam no MinIO (app/arquivos.py)
        import arquivos
        try:
            nome, conteudo = arquivos.ler(r[0])
        except Exception as e:                       # noqa: BLE001
            app.logger.warning("download %s: %s", r[0], e)
            raise ErroApi("Arquivo não encontrado no armazenamento.", 404) from e
        return send_file(conteudo, as_attachment=True, download_name=nome)
    real = _arquivo(r[0])
    return send_file(real, as_attachment=True, download_name=os.path.basename(real))


@app.get("/api/prints/<int:id_print>")
def api_print(id_print):
    with _con() as con:
        r = con.execute("select arquivo from contabil.robo_print where id = %s", (id_print,)).fetchone()
    if not r:
        abort(404)
    return send_file(_arquivo(r[0]))


@app.get("/api/pendencias")
def api_pendencias():
    with _con() as con:
        sigla = _config(con).get("ambiente") or "EMP"
        p = _pendencias(con, sigla)
    p["codigo_livre"] = _codigo_livre()
    return p


@app.post("/api/pendencias/conta")
def api_pendencia_conta():
    """Preenche a conta ERP de uma conta SAP pendente (inclui a linha no plano de contas)."""
    b = request.get_json(silent=True) or {}
    sap, erp = str(b.get("conta_sap") or "").strip(), str(b.get("conta_erp") or "").strip()
    if not sap.isdigit() or not erp.isdigit():
        raise ErroApi("Informe o código numérico da conta ERP.")
    plano = tabelas.ler("plano")
    if any(r["conta_sap"] == sap for r in plano):
        raise ErroApi(f"A conta SAP {sap} já está no plano.")
    existente = next((r for r in plano if r["conta_erp"] == erp), None)
    livre = _codigo_livre()
    if not existente and int(erp) != livre:
        raise ErroApi(f"A conta {erp} não existe no plano ERP. Escolha uma da lista ou use o próximo código livre ({livre}).")
    with _con() as con:
        nome_sap = (con.execute("select nome_sap from contabil.robo_pendencia where tipo = 'conta' and codigo_sap = %s "
                                "limit 1", (sap,)).fetchone() or [""])[0]
    linha = {"conta_sap": sap, "conta_erp": erp,
             "nome_conta": existente["nome_conta"] if existente else nome_sap,
             "sintetica_erp": existente["sintetica_erp"] if existente else "",
             "conta_referencial": existente["conta_referencial"] if existente else ""}
    tabelas.aplicar("plano", incluir=[linha], origem_mudanca=_origem())
    return {"ok": True, "linha": linha, "nova": not existente}


@app.delete("/api/pendencias/conta/<sap>")
def api_pendencia_conta_desfazer(sap):
    tabelas.aplicar("plano", remover=[sap], origem_mudanca=_origem())
    return {"ok": True}


@app.get("/api/alterados")
def api_alterados():
    with _con() as con:
        sigla = _config(con).get("ambiente") or "EMP"
        return {"alterados": _linhas(con.execute(
            "select doc, data_lancamento, lote, campo, antes, depois, detectado_em from contabil.robo_alteracao "
            "where sigla = %s order by detectado_em desc, doc", (sigla,)))}


@app.get("/api/tabelas/<nome>")
def api_tabela(nome):
    if nome not in ("plano", "cc"):
        abort(404)
    return {"linhas": tabelas.ler(nome), "codigo_livre": _codigo_livre() if nome == "plano" else None}


@app.post("/api/tabelas/<nome>")
def api_tabela_salvar(nome):
    """Inclui ou edita uma linha. `chave_anterior` (edição) remove a linha antiga se a chave mudou."""
    if nome not in ("plano", "cc"):
        abort(404)
    d = tabelas.DEFINICOES[nome]
    b = request.get_json(silent=True) or {}
    linha = {c: str(b.get(c) or "").strip() for c in d["campos"]}
    faltando = [d["rotulos"][d["campos"].index(c)] for c in d["obrigatorios"] if not linha[c]]
    if faltando:
        raise ErroApi("Preencha: " + ", ".join(faltando))
    for c in d["numericos"]:
        if linha[c] and not linha[c].isdigit():
            raise ErroApi(f"{d['rotulos'][d['campos'].index(c)]}: '{linha[c]}' precisa ser só número.")
    anterior = str(b.get("chave_anterior") or "").strip()
    chave = linha[d["chave"]]
    if not anterior and any(r[d["chave"]] == chave for r in tabelas.ler(nome)):
        raise ErroApi(f"{d['rotulos'][d['campos'].index(d['chave'])]} {chave} já está na tabela.")
    remover = [anterior] if anterior and anterior != chave else []
    tabelas.aplicar(nome, remover=remover, incluir=[linha], origem_mudanca=_origem())
    return {"ok": True, "linha": linha}


@app.delete("/api/tabelas/<nome>/<chave>")
def api_tabela_excluir(nome, chave):
    if nome not in ("plano", "cc"):
        abort(404)
    tabelas.aplicar(nome, remover=[chave], origem_mudanca=_origem())
    return {"ok": True}


@app.get("/", defaults={"caminho": ""})
@app.get("/<path:caminho>")
def spa(caminho):
    if caminho.startswith("api/"):
        abort(404)
    if caminho and os.path.isfile(os.path.join(WEB, caminho)):
        return send_from_directory(WEB, caminho)
    if not os.path.isfile(os.path.join(WEB, "index.html")):
        return "Frontend não compilado: rode `npm run build` em portal/web/.", 503
    return send_from_directory(WEB, "index.html", max_age=0)
