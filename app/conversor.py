"""Conversão do Razão SAP (ACME) para o layout de importação de lançamentos da ERP.

Reproduz as fórmulas da aba "LANÇAMENTOS" da planilha "MÊS xx.xxxx" (colunas Y..AL),
remove as linhas de valor zero ("NÃO IMPORTAR") e divide o resultado em partes
(abas "1° IMPORTAÇÃO", "2° IMPORTAÇÃO"...) sem quebrar lançamentos.
Detalhes e origem de cada regra: ../README.md
"""
import csv
import datetime as dt
import os
from collections import Counter
from dataclasses import dataclass, field

from python_calamine import CalamineWorkbook

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")

# Linhas de dados por parte. Maior parte observada em 06/2026 = 49.998 linhas (+ cabeçalho).
LIMITE_LINHAS_PARTE = 49_998
# Contas SAP abaixo deste número vão para a filial 200; as demais usam os 3 últimos dígitos da Divisão.
LIMITE_CONTA_FILIAL_200 = 2_999_999_999

CABECALHO_ERP = [
    "Numero do lote",
    "Numero do Lancamento",
    "Numero do registro (partida)",
    "Tipo de lancamento (D ou C)",
    "Data do lancamento (DD/MM/AAAA)",
    "Conta analitica",
    "Valor do lancamento",
    "Complemento do historico",
    "Numero do documento",
    "Centro custo",
    "Valor centro de custo",
    "Codigo da filial",
]

# Colunas do Razão SAP usadas na conversão (nome do cabeçalho normalizado -> chave interna)
COLUNAS_SAP = {
    "nº doc.": "doc",
    "referência": "ref",
    "div": "div",
    "dt.lçto.": "data",
    "mont.em mi": "valor",
    "centro cst": "cc",
    "texto": "texto",
    "razão": "conta",
}


class ErroConversao(Exception):
    pass


@dataclass
class Resultado:
    linhas: list                      # linhas no layout ERP (sem lote), já sem as de valor zero
    partes: list                      # lista de (inicio, fim) sobre `linhas`
    total_sap: int = 0
    zeradas: int = 0
    lancamentos: int = 0
    total_debito: float = 0.0
    total_credito: float = 0.0
    periodo: tuple = (None, None)
    erros: list = field(default_factory=list)    # impedem gerar o arquivo
    avisos: list = field(default_factory=list)   # geram o arquivo, mas precisam de conferência
    # Pendências que o usuário resolve preenchendo no site (tabelas de apoio)
    pend_contas: list = field(default_factory=list)      # contas SAP sem conta ERP (bloqueia)
    pend_duplicadas: list = field(default_factory=list)  # contas SAP com 2+ contas ERP no plano (bloqueia)
    pend_cc: list = field(default_factory=list)          # centros de custo sem de-para (sai 0; não bloqueia)
    ja_lancadas: int = 0                                 # modo complementar: linhas de documentos já importados (ficam de fora)

    @property
    def bloqueado(self):
        return bool(self.erros or self.pend_contas or self.pend_duplicadas)


def _br(v):
    """1234567.8 -> '1.234.567,80' (padrão brasileiro nas mensagens)."""
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _cod(v):
    """Normaliza códigos (conta, centro de custo) vindos como número ou texto."""
    if v is None or v == "":
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    try:
        return str(int(float(s)))
    except ValueError:
        return s


def _texto_excel(v):
    """Como o Excel converte a célula em texto dentro de CONCATENATE/RIGHT."""
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, (dt.date, dt.datetime)):
        # O Excel guarda data como número de série e é esse número que entra no texto
        return str(_serial_excel(v))
    return str(v)


def _serial_excel(d):
    if isinstance(d, dt.datetime):
        d = d.date()
    return (d - dt.date(1899, 12, 30)).days


def montar_tabelas(plano_linhas, cc_linhas, contas_sap_linhas):
    """(plano, duplicadas, cc, nomes_sap) a partir das linhas das tabelas de apoio (dicts)."""
    plano = {}
    duplicadas = {}
    for r in plano_linhas:
        sap, erp = _cod(r["conta_sap"]), _cod(r["conta_erp"])
        if sap in plano and plano[sap] != erp:
            duplicadas.setdefault(sap, {plano[sap]}).add(erp)
        plano[sap] = erp
    cc = {_cod(r["centro_custo_sap"]): _cod(r["centro_custo_erp"]) for r in cc_linhas}
    nomes_sap = {_cod(r["conta_sap"]): r["nome_conta_sap"] for r in contas_sap_linhas}
    return plano, duplicadas, cc, nomes_sap


def carregar_tabelas(pasta=DADOS):
    def ler(nome):
        with open(os.path.join(pasta, nome), newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    return montar_tabelas(ler("plano_contas.csv"), ler("centro_custo.csv"), ler("contas_sap.csv"))


def ler_razao_sap(caminho, avisos=None):
    """Lê o Razão SAP em qualquer um dos formatos conhecidos e devolve as linhas em ordem de Nº doc.

    - .xlsx (como o RAZÃO 06.2026): já vem sem cabeçalhos/subtotais e ordenado por Nº doc.
    - texto do SAP com extensão .xls (lista "não convertida", agrupada por conta): ver ler_razao_texto.
    """
    with open(caminho, "rb") as fh:
        assinatura = fh.read(8)
    if assinatura.startswith(b"PK") or assinatura.startswith(b"\xd0\xcf\x11\xe0"):
        return list(_ler_razao_planilha(caminho))
    return ler_razao_texto(caminho, avisos if avisos is not None else [])


def razao_de_linhas(linhas):
    """Linhas com as colunas do Razão pelo nome do SAP ("Nº doc.", "Dt.lçto."…) -> formato interno do converter."""
    return [{COLUNAS_SAP[k.strip().lower()]: v for k, v in l.items() if k.strip().lower() in COLUNAS_SAP} for l in linhas]


def _mapear_cabecalho(cab):
    idx = {}
    for i, nome in enumerate(cab):
        chave = COLUNAS_SAP.get(str(nome or "").strip().lower())
        if chave and chave not in idx:
            idx[chave] = i
    faltando = [n for n, k in COLUNAS_SAP.items() if k not in idx]
    if faltando:
        raise ErroConversao(
            "O arquivo não parece ser o Razão do SAP: faltam as colunas " + ", ".join(faltando)
        )
    return idx


def _ler_razao_planilha(caminho):
    wb = CalamineWorkbook.from_path(caminho)
    ws = wb.get_sheet_by_index(0)
    it = iter(ws.iter_rows())
    idx = _mapear_cabecalho(next(it))
    for row in it:
        if all(c in ("", None) for c in row):
            continue
        yield {k: row[i] if i < len(row) else None for k, i in idx.items()}


def _num_br(s):
    """'9.500,00' / '-99,00' / '99,00-' -> float"""
    s = s.strip()
    neg = s.endswith("-") or s.startswith("-")
    s = s.strip("-").replace(".", "").replace(",", ".")
    v = float(s)
    return -v if neg else v


def _como_excel(s):
    """Ao abrir o texto do SAP, o Excel transforma campos só com dígitos em número (perde zeros à esquerda).
    Isso é replicado para o resultado continuar igual ao processo manual. Campos que o Excel
    transformaria em data (ex.: '22-1', '05/2026') ficam como o texto original."""
    t = s.strip()
    if t.lstrip("-").isdigit() and t.count("-") <= 1:
        return float(int(t))
    return s  # sem strip: o Excel mantém espaços no começo do texto (ex.: " EG FIANÇA COMARY")


def _decodificar(linha):
    # o arquivo mistura Latin-1 (maioria) com textos em UTF-8
    try:
        return linha.decode("utf-8")
    except UnicodeDecodeError:
        return linha.decode("cp1252", errors="replace")


def ler_razao_texto(caminho, avisos):
    """Razão SAP exportado como texto separado por tabulação (extensão .xls, agrupado por conta).

    Estrutura: para cada conta, "Conta do Razão", "Empresa", "Ledger", cabeçalho, linhas de partida
    e as linhas de subtotal "*" e "** Conta xxxx  valor". Cabeçalhos e subtotais são descartados,
    cada conta é conferida com o subtotal "**" do SAP e o resultado é ordenado por Nº doc
    (mesma ordem do RAZÃO .xlsx usado até hoje: Nº doc crescente, contas em ordem dentro do doc).
    Quando o arquivo está completo, o SAP termina com o bloco de total geral ("Conta do Razão *"
    e a linha "***"), que é conferido com a soma de todas as linhas.
    """
    with open(caminho, "rb") as fh:
        linhas = fh.read().split(b"\n")
    idx = None
    registros = []
    conta_bloco = None
    soma_bloco = 0.0
    divergentes = []
    contas_conferidas = 0
    soma_geral = 0  # em centavos: somar 400 mil floats acumula erro de arredondamento
    total_geral = None  # linha "***" do SAP, só existe quando o arquivo terminou de ser gravado
    linhas_cortadas = []
    for nlin, bruto in enumerate(linhas, start=1):
        linha = _decodificar(bruto.rstrip(b"\r"))
        if not linha.strip():
            continue
        campos = linha.split("\t")
        primeiro = campos[0].strip()
        if primeiro.startswith("Conta do Raz"):
            if conta_bloco is not None:
                divergentes.append(f"conta {conta_bloco} sem linha de subtotal (**)")
            conta_bloco = next((c.strip() for c in campos[1:] if c.strip()), "?")
            if conta_bloco == "*":  # bloco do total geral, no fim do arquivo: não é uma conta
                conta_bloco = None
            soma_bloco = 0.0
            continue
        if primeiro:  # Empresa, Ledger...
            continue
        if any(c.strip() == "Nº doc." for c in campos):  # cabeçalho, repetido em cada conta
            idx = _mapear_cabecalho(campos)
            continue
        if idx is None:
            continue
        marca = campos[1].strip() if len(campos) > 1 else ""
        if marca.startswith("*"):
            if marca == "***":
                total_geral = next((_num_br(c) for c in campos[2:] if c.strip() and c.strip()[-1].isdigit()), None)
            elif marca == "**" and conta_bloco is not None:
                total = next((_num_br(c) for c in campos[3:] if c.strip() and c.strip()[-1].isdigit()), None)
                if total is None or abs(total - soma_bloco) >= 0.005:
                    divergentes.append(f"conta {conta_bloco}: soma das linhas {_br(soma_bloco)} x subtotal SAP {_br(total) if total is not None else "ausente"}")
                contas_conferidas += 1
                conta_bloco = None
            continue
        doc = campos[idx["doc"]].strip() if len(campos) > idx["doc"] else ""
        if not doc.isdigit():
            continue
        if len(campos) <= max(idx.values()):
            # linha cortada (fim do arquivo): não dá para ler valor/conta, então fica de fora
            linhas_cortadas.append(f"{nlin} (Nº doc. {doc})")
            continue
        valor = _num_br(campos[idx["valor"]])
        data = dt.datetime.strptime(campos[idx["data"]].strip(), "%d.%m.%Y").date()
        soma_bloco += valor
        soma_geral += round(valor * 100)
        registros.append({
            "doc": float(int(doc)),
            "ref": _como_excel(campos[idx["ref"]]),
            "div": _como_excel(campos[idx["div"]]),
            "data": data,
            "valor": valor,
            "cc": campos[idx["cc"]].strip(),
            "texto": _como_excel(campos[idx["texto"]]),
            "conta": campos[idx["conta"]].strip(),
        })
    if idx is None:
        raise ErroConversao("O arquivo não parece ser o Razão do SAP (não achei o cabeçalho com 'Nº doc.').")
    # O arquivo é convertido do jeito que veio. Se o SAP não gravou o fim (subtotal da última conta
    # e total geral), só avisa: as contas completas já foram conferidas com os subtotais.
    if linhas_cortadas:
        avisos.append(
            f"{len(linhas_cortadas)} linha(s) do arquivo terminam no meio e ficaram de fora da conversão: "
            + ", ".join(linhas_cortadas[:5]) + "."
        )
    if conta_bloco is not None:
        avisos.append(
            f"A última conta do arquivo ({conta_bloco}) não tem a linha de subtotal (**) do SAP: "
            "foi convertida com as linhas que vieram, sem conferência."
        )
    if total_geral is not None and round(total_geral * 100) != soma_geral:
        avisos.append(f"A soma de todas as linhas ({_br(soma_geral / 100)}) não bate com o total geral do SAP (***) {_br(total_geral)}.")
        total_geral = None
    if divergentes:
        raise ErroConversao("As linhas não batem com os subtotais do SAP: " + "; ".join(divergentes[:10]))
    avisos.append(
        f"Arquivo texto do SAP: {contas_conferidas} contas conferidas com o subtotal do próprio SAP"
        + (" e com o total geral (***)." if total_geral is not None else ".")
    )
    registros.sort(key=lambda r: r["doc"])  # sort estável: mantém a ordem das contas dentro do doc
    return registros


def chave_linha(r):
    """Identifica uma linha do razão (só para comparar um razão com outro; vale dentro de um mesmo processo)."""
    d = r["data"]
    if isinstance(d, dt.datetime):
        d = d.date()
    v = r["valor"]
    if isinstance(v, (int, float)):
        v = round(v, 2)
    return hash((_cod(r["doc"]), _texto_excel(r["ref"]), _cod(r["div"]), d, v,
                 _cod(r["cc"]), _texto_excel(r["texto"]), _cod(r["conta"])))


def converter(caminho_sap, limite=LIMITE_LINHAS_PARTE, tabelas=None, excluir_docs=None, lanc_inicial=0, coletar=None,
              linhas_sap=None):
    """Converte o razão. Modo complementar: `excluir_docs` (Nº doc. já importados, normalizados com _cod) ficam
    de fora e a numeração dos lançamentos continua de `lanc_inicial`. `coletar(n, linha)` vê toda linha lida.
    `linhas_sap` (de razao_de_linhas) substitui a leitura do arquivo: o robô diário converte direto da extração."""
    plano, duplicadas, mapa_cc, nomes_sap = tabelas or carregar_tabelas()
    res = Resultado(linhas=[], partes=[])

    contas_faltando = {}
    contas_duplicadas = set()
    cc_faltando = {}
    saldo_lanc = {}
    celulas_data = []
    historico_vazio = []

    doc_anterior = object()
    lanc = lanc_inicial
    partida = 0
    dmin = dmax = None

    fonte = linhas_sap if linhas_sap is not None else ler_razao_sap(caminho_sap, res.avisos)
    for n, r in enumerate(fonte, start=2):
        res.total_sap += 1
        if coletar:
            coletar(n, r)
        if excluir_docs is not None and _cod(r["doc"]) in excluir_docs:
            res.ja_lancadas += 1
            continue
        # AA/AB: novo lançamento sempre que o Nº doc. muda em relação à linha anterior
        if r["doc"] != doc_anterior:
            lanc += 1
            partida = 0
            doc_anterior = r["doc"]
        # AC: partida sequencial dentro do lançamento (conta também as linhas zeradas)
        partida += 1

        valor = r["valor"]
        if not isinstance(valor, (int, float)):
            res.erros.append(f"Linha {n}: valor inválido ({valor!r})")
            continue
        if valor == 0:  # AD = "NÃO IMPORTAR"
            res.zeradas += 1
            continue
        tipo = "C" if valor < 0 else "D"
        abs_valor = abs(valor)

        data = r["data"]
        if isinstance(data, dt.datetime):
            data = data.date()
        if not isinstance(data, dt.date):
            res.erros.append(f"Linha {n}: data inválida ({data!r})")
            continue
        dmin = data if dmin is None or data < dmin else dmin
        dmax = data if dmax is None or data > dmax else dmax

        # AF: conta ERP pelo PLANO (conta SAP -> analítico)
        conta_sap = _cod(r["conta"])
        conta_erp = plano.get(conta_sap)
        if conta_erp is None:
            pc = contas_faltando.setdefault(conta_sap, {"linhas": 0, "debito": 0.0, "credito": 0.0, "exemplo": ""})
            pc["linhas"] += 1
            pc["debito" if tipo == "D" else "credito"] += abs_valor
            pc["exemplo"] = pc["exemplo"] or _texto_excel(r["texto"])
        if conta_sap in duplicadas:
            contas_duplicadas.add(conta_sap)

        # AH: TEXTO & " - DOC " & Referência ; AI: RIGHT(Referência, 9)
        ref = r["ref"]
        ref_txt = _texto_excel(ref)
        historico = f"{_texto_excel(r['texto'])} - DOC {ref_txt}"
        if historico[:1] in ("-", "+", "=", "@"):
            # Texto que o Excel confunde com fórmula. Mantém o resultado da fórmula (como em 06/2026);
            # em 08/2026 esses históricos foram importados em branco. Ver README.md.
            historico_vazio.append(n)
        documento = ref_txt[-9:]
        if isinstance(r["texto"], (dt.date, dt.datetime)) or isinstance(ref, (dt.date, dt.datetime)):
            celulas_data.append(n)
        # DIREITA() do Excel devolve texto: o nº do documento fica texto, com zeros à esquerda ("000767672").
        # Conferido em 16/10/2026 contra a IMPORTAÇÃO de 10/2026 do Matheus (todos os documentos são texto).

        # AJ/AK: centro de custo ERP + valor, só quando há Centro cst no SAP
        cc_sap = _cod(r["cc"])
        if cc_sap in ("", "0"):
            cc_erp, valor_cc = "", ""
        else:
            cc_erp = mapa_cc.get(cc_sap)
            if cc_erp is None:
                pc = cc_faltando.setdefault(cc_sap, {"linhas": 0, "valor": 0.0, "exemplo": "", "conta": conta_sap})
                pc["linhas"] += 1
                pc["valor"] += abs_valor
                pc["exemplo"] = pc["exemplo"] or _texto_excel(r["texto"])
                cc_erp = 0  # comportamento da planilha (SUMIF sem correspondência = 0)
            else:
                cc_erp = int(cc_erp)
            valor_cc = abs_valor

        # AL: filial
        try:
            conta_num = int(conta_sap)
        except ValueError:
            res.erros.append(f"Linha {n}: conta SAP inválida ({r['conta']!r})")
            continue
        if conta_num < LIMITE_CONTA_FILIAL_200:
            filial = 200
        else:
            filial = int(_texto_excel(r["div"])[-3:])

        res.linhas.append([
            lanc, partida, tipo, data,
            int(conta_erp) if conta_erp is not None else None,
            abs_valor, historico, documento, cc_erp, valor_cc, filial,
        ])
        saldo_lanc[lanc] = saldo_lanc.get(lanc, 0.0) + (abs_valor if tipo == "D" else -abs_valor)
        if tipo == "D":
            res.total_debito += abs_valor
        else:
            res.total_credito += abs_valor

    res.lancamentos = len(saldo_lanc)
    res.periodo = (dmin, dmax)

    if res.total_sap == 0:
        res.erros.append("A planilha não tem linhas de lançamento.")
    for conta, info in sorted(contas_faltando.items()):
        res.pend_contas.append({"conta": conta, "nome_sap": nomes_sap.get(conta, ""), **info})
    for conta in sorted(contas_duplicadas):
        res.pend_duplicadas.append({"conta": conta, "opcoes": sorted(duplicadas[conta], key=int)})
    for cc, info in sorted(cc_faltando.items()):
        res.pend_cc.append({"cc": cc, **info})
    if celulas_data:
        ex = ", ".join(str(x) for x in celulas_data[:10])
        res.avisos.append(
            f"{len(celulas_data)} linha(s) do SAP têm Referência ou Texto que o Excel transformou em data "
            f"(ex.: linhas {ex}). Saem como número de série (ex.: DOC 46044), igual à planilha atual."
        )
    if historico_vazio:
        ex = ", ".join(str(x) for x in historico_vazio[:10])
        res.avisos.append(
            f"{len(historico_vazio)} linha(s) com histórico começando com '-' (Texto do SAP como '-4500419896'). "
            f"Saem com o texto da fórmula, ex.: '-4500419896 - DOC ' (em 06/2026 foi assim; em 08/2026 foram em branco). "
            f"Linhas do SAP: {ex}."
        )
    # Débito x crédito não bloqueia: o arquivo é convertido como veio (decisão de 28/09/2026).
    # Acontece quando o SAP não grava o arquivo até o fim: documentos ficam só com um dos lados.
    desbal = [(k, v) for k, v in saldo_lanc.items() if abs(v) >= 0.005]
    if desbal:
        res.avisos.append(
            f"{len(desbal)} lançamento(s) não fecham débito x crédito e foram gerados assim mesmo "
            f"(a ERP pode recusar a parte que tiver algum deles): "
            + "; ".join(f"{k} (diferença {_br(v)})" for k, v in desbal[:20])
            + (f"; ... e mais {len(desbal) - 20}." if len(desbal) > 20 else ".")
        )
    if abs(res.total_debito - res.total_credito) >= 0.005:
        res.avisos.append(
            f"Total de débitos ({_br(res.total_debito)}) diferente do total de créditos ({_br(res.total_credito)}): "
            f"diferença {_br(res.total_debito - res.total_credito)}."
        )

    res.partes = dividir(res.linhas, limite)
    return res


def converter_complementar(caminho_novo, anteriores, limite=LIMITE_LINHAS_PARTE, tabelas=None):
    """Razão complementar: só os lançamentos (Nº doc.) que não estavam nos razões já importados.

    `anteriores`: [(caminho, nome)] dos razões já lançados, na ordem em que foram importados na ERP
    (o original e, se houver, os complementares anteriores). Cada razão é o mês inteiro de novo; a
    numeração dos lançamentos e dos lotes continua de onde a última importação parou.
    Devolve (resultado, info).
    """
    docs_ant = set()
    lanc_max = 0
    partes_ant = 0
    base = None
    ultimo = Counter()     # linhas do último razão já lançado (é o retrato mais recente do mês)
    doc_de = {}
    for caminho, nome in anteriores:
        contagem = Counter()
        docs_aqui = set()
        doc_aqui_de = {}

        def coletar(n, r, contagem=contagem, docs_aqui=docs_aqui, doc_aqui_de=doc_aqui_de):
            h = chave_linha(r)
            contagem[h] += 1
            doc = _cod(r["doc"])
            docs_aqui.add(doc)
            doc_aqui_de[h] = doc

        try:
            r0 = converter(caminho, limite, tabelas, excluir_docs=frozenset(docs_ant) if docs_ant else None,
                           lanc_inicial=lanc_max, coletar=coletar)
        except ErroConversao as e:
            raise ErroConversao(f"Razão já lançado '{nome}': {e}")
        if base is None:
            base = lote_base(r0)
        if r0.linhas:
            lanc_max = max(l[0] for l in r0.linhas)
        partes_ant += len(r0.partes)
        docs_ant |= docs_aqui
        ultimo, doc_de = contagem, doc_aqui_de
        del r0

    chegadas = []   # linhas do razão novo cujo documento já estava importado

    def coletar_novo(n, r):
        doc = _cod(r["doc"])
        if doc in docs_ant:
            chegadas.append((chave_linha(r), n, doc))

    res = converter(caminho_novo, limite, tabelas, excluir_docs=docs_ant, lanc_inicial=lanc_max, coletar=coletar_novo)
    # confronta as linhas dos documentos já importados: o que sobrou de um lado ou do outro vira aviso
    restante = Counter(ultimo)
    novas_em_doc = []
    for h, n, doc in chegadas:
        if restante[h] > 0:
            restante[h] -= 1
        else:
            novas_em_doc.append((n, doc))
    sumidas = [doc_de[h] for h, c in restante.items() for _ in range(c) if c > 0]
    if novas_em_doc:
        docs = sorted({d for _, d in novas_em_doc})
        res.avisos.append(
            f"{len(novas_em_doc)} linha(s) são novas dentro de {len(docs)} documento(s) que já estavam na importação "
            f"anterior e NÃO entraram na planilha (a ERP já tem esses lançamentos): documentos "
            + ", ".join(docs[:15]) + (f" e mais {len(docs) - 15}" if len(docs) > 15 else "")
            + ". Linhas do arquivo: " + ", ".join(str(n) for n, _ in novas_em_doc[:10]) + "."
        )
    if sumidas:
        docs = sorted(set(sumidas))
        res.avisos.append(
            f"{len(sumidas)} linha(s) do razão já lançado não aparecem no razão novo (documentos "
            + ", ".join(docs[:15]) + (f" e mais {len(docs) - 15}" if len(docs) > 15 else "")
            + "). O que já foi importado na ERP continua lá; confira se houve estorno ou exclusão no SAP."
        )
    if not res.linhas and not res.erros:
        res.erros.append("Não há lançamentos novos: todos os documentos do razão novo já estavam nos razões já lançados.")
    info = {
        "lanc_inicial": lanc_max + 1, "lote_inicial": base + partes_ant,
        "linhas_ja_lancadas": res.ja_lancadas, "documentos_ja_lancados": len(docs_ant),
        "novas_em_documento_lancado": len(novas_em_doc), "linhas_sumidas": len(sumidas),
    }
    return res, info


def dividir(linhas, limite=LIMITE_LINHAS_PARTE):
    """Agrupa lançamentos inteiros em partes de até `limite` linhas (guloso)."""
    partes = []
    inicio = 0
    i = 0
    n = len(linhas)
    while i < n:
        j = i
        while j < n and linhas[j][0] == linhas[i][0]:
            j += 1
        if j - i > limite:
            raise ErroConversao(f"O lançamento {linhas[i][0]} tem {j - i} linhas, mais que o limite de {limite} por parte.")
        if j - inicio > limite:
            partes.append((inicio, i))
            inicio = i
        i = j
    if inicio < n:
        partes.append((inicio, n))
    return partes


def lote_base(res):
    """Lote da 1ª parte: mês de competência x 100.000 + 1 (06/2026 -> 600001)."""
    d = res.periodo[0]
    return d.month * 100_000 + 1 if d else 1


def gravar_xlsx(res, destino, lote_inicial=None, incluir_original=True, complementar=False):
    """Gera o .xlsx com a aba ORIGINAL (sem lote) + uma aba por parte (lote = lote_inicial, +1, ...).

    Complementar: uma aba "COMPLEMENTAR" com o lote preenchido; se passar do limite, uma aba por parte
    ("1° COMPLEMENTAR", ...), cada uma com o seu lote."""
    from xlsx_rapido import Planilha, gravar

    lote_inicial = lote_inicial or lote_base(res)
    base_data = dt.date(1899, 12, 30)
    larguras = [15, 20, 26, 26, 30, 15, 18, 75, 20, 13, 20, 15]
    # 2 centralizado, 3 data, 4 valor (#,##0.00), 5 texto à esquerda
    estilos = [2, 2, 2, 2, 3, 2, 4, 5, 2, 2, 4, 2]

    def gerar(inicio, fim, lote):
        for lanc, partida, tipo, data, conta, valor, hist, doc, cc, vcc, filial in res.linhas[inicio:fim]:
            yield [lote, lanc, partida, tipo, (data - base_data).days, conta, valor, hist, doc, cc, vcc, filial]

    def planilha(nome, inicio, fim, lote):
        p = Planilha(nome, larguras, estilos)
        p.cabecalho = CABECALHO_ERP
        p.linhas = gerar(inicio, fim, lote)
        p.n_linhas = fim - inicio
        return p

    if complementar:
        if len(res.partes) == 1:
            gravar(destino, [planilha("COMPLEMENTAR", 0, len(res.linhas), lote_inicial)])
        else:
            gravar(destino, [planilha(f"{p}° COMPLEMENTAR", ini, fim, lote_inicial + p - 1)
                             for p, (ini, fim) in enumerate(res.partes, start=1)])
        return
    abas = [planilha("ORIGINAL", 0, len(res.linhas), None)] if incluir_original else []
    abas += [planilha(f"{p}° IMPORTAÇÃO", ini, fim, lote_inicial + p - 1)
             for p, (ini, fim) in enumerate(res.partes, start=1)]
    gravar(destino, abas)
