"""Conversor Razão SAP (ACME) -> planilha de importação ERP: API + frontend (web/dist).

Desenvolvimento:  .venv/bin/python app/app.py        (porta 8090; CONTABIL_PORTA muda)
Produção (k3s):   gunicorn --chdir app app:app       (ver Dockerfile)
"""
import datetime as dt
import json
import os
import shutil
import threading
import time
import uuid

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

import conversor
import tabelas

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.environ.get("CONTABIL_WEB", os.path.join(BASE, "..", "web", "dist"))
# trabalhos/<id>/: entrada (arquivo enviado), meta.json, resultado.json, saida.xlsx
TRABALHOS = os.environ.get("CONTABIL_TRABALHOS", os.path.join(BASE, "trabalhos"))
FALHAS = os.environ.get("CONTABIL_FALHAS", os.path.join(BASE, "falhas"))  # uploads ilegíveis, para análise
MANTER_TRABALHOS_HORAS = 24
os.makedirs(TRABALHOS, exist_ok=True)
os.makedirs(FALHAS, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 600 * 1024 * 1024  # modo complementar envia 2+ razões de ~35 MB cada
app.json.ensure_ascii = False
# cada conversão chega a ~700 MB de memória: no máximo 2 ao mesmo tempo
conversoes = threading.BoundedSemaphore(2)


class ErroApi(Exception):
    def __init__(self, mensagem, status=400, **extra):
        super().__init__(mensagem)
        self.mensagem, self.status, self.extra = mensagem, status, extra


@app.errorhandler(ErroApi)
def _erro_api(e):
    return jsonify({"erro": e.mensagem, **e.extra}), e.status


@app.errorhandler(413)
def _grande(_):
    return jsonify({"erro": "Os arquivos juntos passam de 600 MB."}), 413


def limpar_trabalhos():
    limite = time.time() - MANTER_TRABALHOS_HORAS * 3600
    for nome in os.listdir(TRABALHOS):
        p = os.path.join(TRABALHOS, nome)
        if os.path.getmtime(p) < limite:
            shutil.rmtree(p, ignore_errors=True)


def pasta_trabalho(id_trab):
    p = os.path.join(TRABALHOS, id_trab)
    if not id_trab.isalnum() or not os.path.isdir(p):
        raise ErroApi("Esse arquivo expirou (fica 24 h) ou não existe. Envie o razão de novo.", 404)
    return p


def _json_data(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v


def processar(id_trab):
    """Converte o arquivo do trabalho com as tabelas atuais e grava resultado.json (+ saida.xlsx)."""
    pasta = pasta_trabalho(id_trab)
    with open(os.path.join(pasta, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    entrada = os.path.join(pasta, "entrada")
    complementar = meta.get("modo") == "complementar"
    anteriores = [(os.path.join(pasta, f"anterior{i}"), nome) for i, nome in enumerate(meta.get("anteriores", []))]
    info = None
    t0 = time.time()
    if not conversoes.acquire(timeout=120):
        raise ErroApi("O servidor está ocupado com outras conversões. Tente de novo em 1 minuto.", 503)
    try:
        try:
            if complementar:
                res, info = conversor.converter_complementar(
                    entrada, anteriores, limite=meta["limite"], tabelas=tabelas.carregar_para_conversao())
            else:
                res = conversor.converter(entrada, limite=meta["limite"], tabelas=tabelas.carregar_para_conversao())
        except conversor.ErroConversao as e:
            raise ErroApi(str(e), 422)
        except ErroApi:
            raise
        except Exception as e:  # arquivo que não é planilha, corrompido etc.
            carimbo = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy(entrada, os.path.join(FALHAS, f"{carimbo} - {meta['arquivo']}"))
            raise ErroApi(f"Não consegui ler o arquivo: {e}", 422)

        lote = meta["lote"] or (info["lote_inicial"] if complementar else conversor.lote_base(res))
        partes = []
        for i, (a, b) in enumerate(res.partes, start=1):
            fatia = res.linhas[a:b]
            partes.append({
                "numero": i, "lote": lote + i - 1, "linhas": b - a,
                "lancamento_de": fatia[0][0], "lancamento_ate": fatia[-1][0],
                "debito": round(sum(x[5] for x in fatia if x[2] == "D"), 2),
                "credito": round(sum(x[5] for x in fatia if x[2] == "C"), 2),
            })
        saida = os.path.join(pasta, "saida.xlsx")
        if os.path.exists(saida):
            os.remove(saida)
        if not res.bloqueado:
            conversor.gravar_xlsx(res, saida, lote_inicial=lote, complementar=complementar)
    finally:
        conversoes.release()

    codigos = [int(r["conta_erp"]) for r in tabelas.ler("plano") if str(r["conta_erp"]).isdigit()]
    resultado = {
        "id": id_trab,
        "arquivo": meta["arquivo"],
        "modo": "complementar" if complementar else "primeira",
        "nome_saida": (
            f"IMPORTAÇÃO {res.periodo[0].month:02d}.{res.periodo[0].year} - COMPLEMENTAR.xlsx"
            if complementar and res.periodo[0]
            else f"IMPORTAÇÃO ERP - {os.path.splitext(meta['arquivo'])[0]}.xlsx"),
        "complementar": ({**info, "anteriores": meta["anteriores"]} if complementar else None),
        "pronto": not res.bloqueado,
        "segundos": round(time.time() - t0, 1),
        "periodo": [_json_data(res.periodo[0]), _json_data(res.periodo[1])],
        "totais": {
            "linhas_sap": res.total_sap, "linhas_zeradas": res.zeradas, "linhas_importar": len(res.linhas),
            "lancamentos": res.lancamentos,
            "debito": round(res.total_debito, 2), "credito": round(res.total_credito, 2),
        },
        "erros": res.erros,
        "avisos": res.avisos,
        "pendencias": {
            "contas": [{**p, "debito": round(p["debito"], 2), "credito": round(p["credito"], 2)} for p in res.pend_contas],
            "duplicadas": res.pend_duplicadas,
            "centros_custo": [{**p, "valor": round(p["valor"], 2)} for p in res.pend_cc],
        },
        "maior_conta_erp": max(codigos) if codigos else None,
        "partes": partes,
    }
    with open(os.path.join(pasta, "resultado.json"), "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False)
    return resultado


# ---------------------------------------------------------------- API

@app.get("/health")
def health():
    return {"ok": True, "tabelas": tabelas.origem()}


@app.post("/api/converter")
def api_converter():
    limpar_trabalhos()
    arq = request.files.get("razao")
    complementar = request.form.get("modo") == "complementar"
    anteriores = [a for a in request.files.getlist("anteriores") if a and a.filename]
    if not arq or not arq.filename:
        raise ErroApi("Escolha o arquivo do Razão SAP novo." if complementar else "Escolha o arquivo do Razão SAP.")
    if complementar and not anteriores:
        raise ErroApi("Envie também o razão que já foi importado (o original do mês), para eu saber o que é novo.")
    try:
        limite = int(request.form.get("limite") or conversor.LIMITE_LINHAS_PARTE)
        lote = int(request.form["lote"]) if request.form.get("lote") else None
    except ValueError:
        raise ErroApi("Limite de linhas e lote precisam ser números.")
    if limite < 100:
        raise ErroApi("O limite de linhas por parte precisa ser pelo menos 100.")
    id_trab = uuid.uuid4().hex
    pasta = os.path.join(TRABALHOS, id_trab)
    os.makedirs(pasta)
    arq.save(os.path.join(pasta, "entrada"))
    for i, a in enumerate(anteriores if complementar else []):
        a.save(os.path.join(pasta, f"anterior{i}"))
    with open(os.path.join(pasta, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"arquivo": os.path.basename(arq.filename), "limite": limite, "lote": lote,
                   "modo": "complementar" if complementar else "primeira",
                   "anteriores": [os.path.basename(a.filename) for a in anteriores] if complementar else []}, fh)
    try:
        return processar(id_trab)
    except ErroApi:
        shutil.rmtree(pasta, ignore_errors=True)
        raise


@app.get("/api/trabalhos/<id_trab>")
def api_trabalho(id_trab):
    with open(os.path.join(pasta_trabalho(id_trab), "resultado.json"), encoding="utf-8") as fh:
        return json.load(fh)


@app.post("/api/trabalhos/<id_trab>/pendencias")
def api_pendencias(id_trab):
    """Grava o que foi preenchido na tela nas tabelas e reprocessa o mesmo arquivo.

    Corpo: {"contas": {"<sap>": {"conta_erp": "808", "nome_conta": "..."}},
            "duplicadas": {"<sap>": "<conta erp escolhida>"},
            "centros_custo": {"<cc sap>": "<cc erp>"}}
    """
    pasta_trabalho(id_trab)
    corpo = request.get_json(silent=True) or {}
    contas = {k: v for k, v in (corpo.get("contas") or {}).items() if str(v.get("conta_erp", "")).strip()}
    dups = {k: str(v) for k, v in (corpo.get("duplicadas") or {}).items() if str(v).strip()}
    ccs = {k: str(v).strip() for k, v in (corpo.get("centros_custo") or {}).items() if str(v).strip()}
    erros = []
    for sap, v in contas.items():
        if not str(v["conta_erp"]).strip().isdigit():
            erros.append(f"Conta ERP '{v['conta_erp']}' (conta SAP {sap}) precisa ser só número.")
    for cc, v in ccs.items():
        if not v.isdigit():
            erros.append(f"Centro de custo ERP '{v}' (CC SAP {cc}) precisa ser só número.")
    if erros:
        raise ErroApi("Corrija os campos antes de salvar.", detalhes=erros)

    salvos = []
    if contas or dups:
        usadas = {conversor._cod(r["conta_erp"]): conversor._cod(r["conta_sap"]) for r in tabelas.ler("plano")}
        novas = []
        for sap, v in contas.items():
            erp = str(v["conta_erp"]).strip()
            dono = usadas.get(erp)
            if dono and dono != sap:
                salvos.append(f"atenção: a conta ERP {erp} também é usada pela conta SAP {dono}")
            novas.append({"conta_sap": sap, "conta_erp": erp, "nome_conta": v.get("nome_conta", "")})
            salvos.append(f"conta SAP {sap} → ERP {erp}")
        for sap, erp in dups.items():
            salvos.append(f"conta SAP {sap} ficou só com a conta ERP {erp}")
        tabelas.aplicar("plano", incluir=novas, manter_so=dups)
    if ccs:
        tabelas.aplicar("cc", incluir=[
            {"centro_custo_sap": cc, "centro_custo_resumido": cc[-5:], "centro_custo_erp": erp}
            for cc, erp in ccs.items()])
        salvos += [f"CC SAP {cc} → ERP {erp}" for cc, erp in ccs.items()]
    resultado = processar(id_trab)
    resultado["salvos"] = salvos
    return resultado


@app.get("/api/trabalhos/<id_trab>/arquivo")
def api_arquivo(id_trab):
    pasta = pasta_trabalho(id_trab)
    p = os.path.join(pasta, "saida.xlsx")
    if not os.path.exists(p):
        raise ErroApi("O arquivo ainda não foi gerado — resolva as pendências primeiro.", 409)
    with open(os.path.join(pasta, "resultado.json"), encoding="utf-8") as fh:
        nome = json.load(fh)["nome_saida"]
    return send_file(p, as_attachment=True, download_name=nome)


@app.get("/api/tabelas/<nome>")
def api_tabela(nome):
    if nome not in ("plano", "cc"):
        abort(404)
    d = tabelas.DEFINICOES[nome]
    return {"campos": d["campos"], "rotulos": d["rotulos"], "chave": d["chave"],
            "obrigatorios": d["obrigatorios"], "linhas": tabelas.ler(nome)}


@app.post("/api/tabelas/<nome>")
def api_tabela_salvar(nome):
    if nome not in ("plano", "cc"):
        abort(404)
    d = tabelas.DEFINICOES[nome]
    linha = {c: str((request.get_json(silent=True) or {}).get(c) or "").strip() for c in d["campos"]}
    faltando = [d["rotulos"][d["campos"].index(c)] for c in d["obrigatorios"] if not linha[c]]
    if faltando:
        raise ErroApi("Preencha: " + ", ".join(faltando))
    for c in d["numericos"]:
        if linha[c] and not linha[c].isdigit():
            raise ErroApi(f"{d['rotulos'][d['campos'].index(c)]}: '{linha[c]}' precisa ser só número.")
    tabelas.aplicar(nome, incluir=[linha])
    return {"ok": True, "linha": linha}


@app.delete("/api/tabelas/<nome>/<chave>")
def api_tabela_excluir(nome, chave):
    if nome not in ("plano", "cc"):
        abort(404)
    tabelas.aplicar(nome, remover=[chave])
    return {"ok": True}


# ---------------------------------------------------------------- frontend (SPA)

@app.get("/", defaults={"caminho": ""})
@app.get("/<path:caminho>")
def spa(caminho):
    if caminho.startswith("api/"):
        abort(404)
    if caminho and os.path.isfile(os.path.join(WEB, caminho)):
        return send_from_directory(WEB, caminho)
    if not os.path.isfile(os.path.join(WEB, "index.html")):
        return "Frontend não compilado: rode `npm run build` em web/.", 503
    return send_from_directory(WEB, "index.html", max_age=0)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("CONTABIL_PORTA", "8090")), threaded=True)
