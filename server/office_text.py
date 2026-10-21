"""Text aus Office-Dateien (OpenDocument und Microsoft-XML) — für den Textauszug
neben hochgeladenen Anhängen, wie bei PDFs.

Beide Formate sind ZIP-Archive mit XML darin; gelesen wird nur das Nötige mit
der Standardbibliothek, ohne LibreOffice. Tabellen kommen als Zeilen mit
Tabulatoren heraus, Folien und Tabellenblätter mit einer Überschrift.
Alte Binärformate (.doc, .xls, .ppt) liefern "" — die kann das Modell selbst
mit soffice umwandeln."""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ODF_EXT = {".odt", ".ods", ".odp", ".odg"}
OOXML_EXT = {".docx", ".pptx", ".xlsx"}
OFFICE_EXT = ODF_EXT | OOXML_EXT

MAX_XML = 64 * 1024 * 1024     # entpackt; schützt vor ZIP-Bomben
MAX_REPEAT = 100               # ODS wiederholt leere Zeilen gern millionenfach
_NS_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_NS_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_NS_DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _xml(z: zipfile.ZipFile, name: str):
    if z.getinfo(name).file_size > MAX_XML:
        raise ValueError(f"{name} zu groß")
    return ET.fromstring(z.read(name))


def _row(cells) -> str:
    cells = [c.replace("\t", " ").replace("\n", " ").strip() for c in cells]
    while cells and not cells[-1]:
        cells.pop()
    return "\t".join(cells)


# ---------- OpenDocument ----------
def _odf_inline(el) -> str:
    out = [el.text or ""]
    for ch in el:
        tag = _local(ch.tag)
        if tag == "s":
            out.append(" " * int(ch.get(f"{{{_NS_TEXT}}}c", "1")))
        elif tag == "tab":
            out.append("\t")
        elif tag == "line-break":
            out.append("\n")
        elif tag not in ("note", "annotation"):     # Fußnoten mitten im Satz stören
            out.append(_odf_inline(ch))
        out.append(ch.tail or "")
    return "".join(out)


def _odf_blocks(el, lines: list) -> None:
    for ch in el:
        tag = _local(ch.tag)
        if tag in ("p", "h"):
            lines.append(_odf_inline(ch))
        elif tag == "table-row":
            cells = []
            for c in ch:
                if _local(c.tag) not in ("table-cell", "covered-table-cell"):
                    continue
                sub: list = []
                _odf_blocks(c, sub)
                n = int(c.get(f"{{{_NS_TABLE}}}number-columns-repeated", "1"))
                cells += [" ".join(sub)] * min(n, MAX_REPEAT)
            row = _row(cells)
            if row:
                n = int(ch.get(f"{{{_NS_TABLE}}}number-rows-repeated", "1"))
                lines += [row] * min(n, MAX_REPEAT)
        elif tag == "table":
            lines += ["", f"### {ch.get(f'{{{_NS_TABLE}}}name', '')}".rstrip()]
            _odf_blocks(ch, lines)
        elif tag == "page":
            lines += ["", f"--- {ch.get(f'{{{_NS_DRAW}}}name', '')} ---"]
            _odf_blocks(ch, lines)
        elif tag not in ("tracked-changes", "annotation", "forms"):
            _odf_blocks(ch, lines)


def _odf(z: zipfile.ZipFile) -> list:
    lines: list = []
    _odf_blocks(_xml(z, "content.xml"), lines)
    return lines


# ---------- Microsoft (docx, pptx) ----------
def _oo_inline(el, out: list) -> None:
    for ch in el:
        tag = _local(ch.tag)
        if tag == "t":
            out.append(ch.text or "")
        elif tag == "tab":
            out.append("\t")
        elif tag in ("br", "cr"):
            out.append("\n")
        elif tag not in ("pPr", "rPr", "delText", "instrText"):   # pPr hat Tabstopps
            _oo_inline(ch, out)


def _oo_blocks(el, lines: list) -> None:
    for ch in el:
        tag = _local(ch.tag)
        if tag == "p":
            out: list = []
            _oo_inline(ch, out)
            lines.append("".join(out))
        elif tag == "tr":
            cells = []
            for c in ch:
                if _local(c.tag) == "tc":
                    sub: list = []
                    _oo_blocks(c, sub)
                    cells.append(" ".join(sub))
            if row := _row(cells):
                lines.append(row)
        else:
            _oo_blocks(ch, lines)


def _nummer(name: str) -> int:
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


def _docx(z: zipfile.ZipFile) -> list:
    lines: list = []
    _oo_blocks(_xml(z, "word/document.xml"), lines)
    return lines


def _pptx(z: zipfile.ZipFile) -> list:
    folien = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                    key=_nummer)
    lines: list = []
    for i, n in enumerate(folien, 1):
        lines += ["", f"--- Folie {i} ---"]
        _oo_blocks(_xml(z, n), lines)
    return lines


def _spalte(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]*", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xlsx(z: zipfile.ZipFile) -> list:
    names = set(z.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in _xml(z, "xl/sharedStrings.xml"):
            shared.append("".join(t.text or "" for t in si.iter()
                                  if _local(t.tag) == "t"))
    ziele = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for rel in _xml(z, "xl/_rels/workbook.xml.rels"):
            t = rel.get("Target", "")
            ziele[rel.get("Id")] = t.lstrip("/") if t.startswith("/") else f"xl/{t}"
    lines: list = []
    for blatt in _xml(z, "xl/workbook.xml").iter():
        if _local(blatt.tag) != "sheet":
            continue
        pfad = ziele.get(blatt.get(f"{{{_NS_REL}}}id"))
        if pfad not in names:
            continue
        lines += ["", f"### {blatt.get('name', '')}"]
        for row in _xml(z, pfad).iter():
            if _local(row.tag) != "row":
                continue
            cells: list = []
            for c in row:
                if _local(c.tag) != "c":
                    continue
                typ = c.get("t")
                v = next((x.text or "" for x in c if _local(x.tag) == "v"), "")
                if typ == "inlineStr":
                    wert = "".join(t.text or "" for t in c.iter() if _local(t.tag) == "t")
                elif typ == "s":
                    wert = shared[int(v)] if v.isdigit() and int(v) < len(shared) else ""
                elif typ == "b":
                    wert = {"1": "TRUE", "0": "FALSE"}.get(v, v)
                else:
                    wert = v
                spalte = _spalte(c.get("r", "")) if c.get("r") else len(cells)
                cells += [""] * (spalte - len(cells))
                cells.append(wert)
            if zeile := _row(cells):
                lines.append(zeile)
    return lines


def text_of(path) -> str:
    """Text einer Office-Datei, "" wenn es kein unterstütztes Format ist oder
    sie sich nicht lesen lässt."""
    ext = Path(path).suffix.lower()
    try:
        with zipfile.ZipFile(path) as z:
            if ext in ODF_EXT:
                lines = _odf(z)
            elif ext == ".docx":
                lines = _docx(z)
            elif ext == ".pptx":
                lines = _pptx(z)
            elif ext == ".xlsx":
                lines = _xlsx(z)
            else:
                return ""
    except Exception:
        return ""
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
