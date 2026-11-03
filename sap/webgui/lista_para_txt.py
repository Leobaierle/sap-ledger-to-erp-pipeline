"""Monta o balancete "não convertido" (como o SAP grava em Lista › Gravar › Arquivo local) a partir da lista do RFBILA00
lida da tela do WebGUI por sap_webgui.mjs (lista.json). Não calcula nada: só copia o texto de cada campo da lista.

Regras do arquivo do SAP (conferidas contra BALANCETE_10.2026.xls exportado à mão em 20/10/2026):
- cp1252 (Windows), linhas com CRLF; título e linha "Brasil ..." como estão; linhas de moldura e vazias saem vazias;
- campos separados por TAB nas posições fixas do RFBILA00; tabs vazios do fim da linha são cortados;
- número com sinal no fim ("2.786,15-") vira "-2.786,15"; positivo mantém os espaços da frente ("       2.268,32").

Uso: lista_para_txt.py lista.json DESTINO.xls
"""
import json
import re
import sys

LARGURA = 140


def _desescapar(s):
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s).replace("\\'", "'").replace("\\\\", "\\")


def itens(lsdatas):
    """[(linha da tela, coluna, tipo, texto)] — tipo TEXT ou IMAGE (linha vertical/moldura)."""
    out = []
    for d in lsdatas:
        m = re.search(r"SID:'wnd\[0\]/usr/lbl\[(\d+),(\d+)\]',Type:'ABAPLIST(\w+)'", d)
        if not m:
            continue
        t = re.search(r"(?:^\{|,)4:'((?:[^'\\]|\\.)*)'", d)
        out.append((int(m.group(2)), int(m.group(1)), m.group(3), _desescapar(t.group(1)) if t else ""))
    return out


def texto_da_linha(campos):
    """Linha em largura fixa: texto na coluna; linha vertical (symbol5) = '|'; outras molduras ignoradas."""
    buf = [" "] * LARGURA
    for col, tipo, txt in campos:
        if tipo == "IMAGE":
            if txt.endswith("symbol5.png"):
                buf[col] = "|"
            continue
        for k, ch in enumerate(txt):
            if col + k < LARGURA:
                buf[col + k] = ch
    return "".join(buf)


def num(s):
    """Número da lista → como o SAP grava: sinal do fim vai para a frente (sem os espaços). Campo estourado
    ("*300,0-") não é número e fica como está."""
    s = s.rstrip()
    if re.fullmatch(r"\s*[\d.]+,\d+-", s):
        return "-" + s[:-1].strip()
    return s.strip() if s.strip().startswith("*") else s


def converter_linha(s):
    """Linha de largura fixa da lista → linha do arquivo "não convertido"."""
    if not s.strip() or set(s.strip()) <= set("|"):
        return ""
    if s.startswith("CONTABIL") or s.startswith("Brasil"):
        return s.rstrip()
    if s.startswith("Empresa"):
        cs = ["Empresa", "", "", "", "", s[14:18].strip(), "Divisão", "", s[36:40].strip(), "", "", "", "",
              "Montantes em", "", s[111:].strip()]
    elif s[3:7].strip().isdigit():                       # linha de conta
        cs = ["", s[1:2].strip(), s[3:7].strip(), s[8:12].strip(), s[13:23].strip(), "", "", s[24:63].rstrip(), "", "",
              num(s[65:81]), "", num(s[84:100]), "", num(s[102:118]), "", num(s[119:126]), s[127:131].strip()]
    elif s[1:63].replace("|", "").strip() == "" and s[127:131].strip().startswith("*"):    # total de nível
        cs = [""] * 10 + [num(s[65:81]), "", num(s[84:100]), "", num(s[102:118]), "", num(s[119:126]),
                          s[127:131].strip()]
    elif s[13:18] in ("Texto", ".....") or s[1:2] in ("V", "S"):                          # cabeçalho das colunas
        cs = ["", s[1:2].strip(), s[3:7].strip(), s[8:12].strip(), s[13:63].rstrip(), "", "", "", "",
              s[64:82].rstrip(), "", s[83:101].rstrip(), "", "", s[102:118].rstrip(), "", s[119:126].rstrip(),
              s[127:131].strip()]
    else:
        raise ValueError(f"linha da lista não reconhecida: {s.rstrip()!r}")
    while cs and cs[-1] == "":
        cs.pop()
    return "\t".join(cs)


def _encaixe(seq, bloco, minimo=1):
    """Maior k tal que o fim de seq é igual ao começo do bloco (só conta k ≥ minimo)."""
    for k in range(min(len(seq), len(bloco)), minimo - 1, -1):
        if seq[-k:] == bloco[:k]:
            return k
    return 0


def linhas_da_lista(dados):
    """Linhas da lista na ordem do arquivo do SAP, montadas pelo CONTEÚDO das telas (a numeração que o WebGUI informa
    fica deslocada em 1 depois de cada página nova, então não serve para encaixar).

    Cada tela: topo fixo (linhas 0–7) = cabeçalho da página corrente (título, Brasil, vazia, Empresa, vazia, V, S,
    moldura); corpo = linhas 8.. . Dentro do corpo, cada página nova vem como uma linha sem nenhum campo (artefato da
    tela, não existe no arquivo do SAP: é descartada) + as 8 linhas de cabeçalho. Quando o P+ para no começo de uma
    página, o pedaço do cabeçalho que não apareceu no corpo está no topo fixo."""
    seq, avisos = None, []
    for tela in dados["telas"]:
        por_linha = {}
        for r, c, tipo, txt in itens(tela["itens"]):
            por_linha.setdefault(r, []).append((c, tipo, txt))
        topo = [texto_da_linha(sorted(por_linha.get(r, []))) for r in range(8)]
        corpo = [texto_da_linha(sorted(por_linha[r])) for r in sorted(por_linha) if r >= 8]
        if seq is None:
            seq = topo + corpo
            continue
        k = _encaixe(seq, corpo, minimo=2)          # sobreposição entre telas (P+ andou menos que uma tela)
        if k:
            seq += corpo[k:]
            continue
        j = _encaixe(seq, topo[:7])                 # P+ pulou o fim do cabeçalho de uma página nova
        if j:
            seq += topo[j:]
        seq += corpo
    if sum(1 for l in seq if l.startswith("CONTABIL")) != sum(1 for l in seq if l.startswith("Brasil")):
        raise ValueError("cabeçalhos de página incompletos na leitura da lista")
    return seq


def main():
    origem, destino = sys.argv[1:3]
    dados = json.load(open(origem, encoding="utf-8"))
    saida = [converter_linha(s) for s in linhas_da_lista(dados)]
    while saida and saida[-1] == "":              # moldura de baixo da tabela: o SAP não grava
        saida.pop()
    with open(destino, "wb") as f:
        f.write("".join(l + "\r\n" for l in saida).encode("cp1252"))
    print(f"{destino}: {len(saida)} linhas")


if __name__ == "__main__":
    main()
