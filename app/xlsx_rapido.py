"""Gravador .xlsx mínimo e rápido (escreve o XML direto), só para o layout de importação ERP.

O xlsxwriter levava ~100 s para as ~820 mil linhas (ORIGINAL + partes); este leva uma fração disso.
Estilos (índices em cellXfs): 0 padrão, 1 cabeçalho, 2 centralizado, 3 data, 4 valor, 5 texto à esquerda.
Uma célula pode trazer o próprio estilo como (valor, estilo).
"""
import zipfile
from xml.sax.saxutils import escape

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font><font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9E1F2"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color auto="1"/></left><right style="thin"><color auto="1"/></right><top style="thin"><color auto="1"/></top><bottom style="thin"><color auto="1"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="left"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

_CT_HEAD = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Planilha:
    def __init__(self, nome, larguras, estilos_coluna):
        self.nome = nome
        self.larguras = larguras
        self.estilos = estilos_coluna   # estilo por coluna (índice cellXfs)
        self.cabecalho = None
        self.linhas = None              # iterável de listas; None/"" = célula vazia
        self.n_linhas = 0


def _xml_planilha(p, fh):
    letras = [_col(i) for i in range(len(p.larguras))]
    ult = letras[-1]
    w = fh.write
    w('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
      '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">')
    w(f'<dimension ref="A1:{ult}{p.n_linhas + 1}"/>')
    w('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>')
    w("<cols>" + "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{lg}" style="{p.estilos[i]}" customWidth="1"/>'
        for i, lg in enumerate(p.larguras)) + "</cols>")
    w("<sheetData>")
    w('<row r="1">' + "".join(
        f'<c r="{letras[i]}1" s="1" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
        for i, v in enumerate(p.cabecalho)) + "</row>")
    buf = []
    for r, linha in enumerate(p.linhas, start=2):
        cel = []
        for i, v in enumerate(linha):
            if v is None or v == "":
                continue
            s = p.estilos[i]
            if isinstance(v, tuple):        # (valor, estilo) quando a célula foge do estilo da coluna
                v, s = v
            if isinstance(v, str):
                cel.append(f'<c r="{letras[i]}{r}" s="{s}" t="inlineStr"><is><t xml:space="preserve">{escape(v)}</t></is></c>')
            else:
                cel.append(f'<c r="{letras[i]}{r}" s="{s}"><v>{v!r}</v></c>')
        buf.append(f'<row r="{r}">{"".join(cel)}</row>')
        if len(buf) >= 5000:
            w("".join(buf))
            buf.clear()
    w("".join(buf))
    w("</sheetData>")
    w(f'<autoFilter ref="A1:{ult}{p.n_linhas + 1}"/>')
    w("</worksheet>")


def gravar(destino, planilhas):
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        ct = _CT_HEAD + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
            for i in range(1, len(planilhas) + 1)) + "</Types>"
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("xl/styles.xml", _STYLES)
        sheets = "".join(
            f'<sheet name="{escape(p.nome)}" sheetId="{i}" r:id="rId{i}"/>' for i, p in enumerate(planilhas, 1))
        nomes = "".join(
            f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
            f"'{escape(p.nome)}'!$A$1:${_col(len(p.larguras) - 1)}${p.n_linhas + 1}</definedName>"
            for i, p in enumerate(planilhas))
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   f"<sheets>{sheets}</sheets><definedNames>{nomes}</definedNames></workbook>")
        rels = "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(planilhas) + 1))
        rels += (f'<Relationship Id="rId{len(planilhas) + 1}" '
                 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                   f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for i, p in enumerate(planilhas, 1):
            with z.open(f"xl/worksheets/sheet{i}.xml", "w", force_zip64=True) as raw:
                import io
                fh = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                _xml_planilha(p, fh)
                fh.flush()
                fh.detach()
