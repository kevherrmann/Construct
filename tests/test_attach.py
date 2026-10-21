"""Anhänge: jede Datei ist erlaubt, Office-Dateien bekommen einen Textauszug
(server/attach.py, server/office_text.py)."""
import zipfile

import pytest

from server import attach, office_text, runs
from server import uploads_gc as gc

ODF = ('<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
       'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
       'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0">'
       '<office:body>{}</office:body></office:document-content>')
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def zip_mit(pfad, dateien: dict):
    with zipfile.ZipFile(pfad, "w") as z:
        for name, inhalt in dateien.items():
            z.writestr(name, inhalt)
    return pfad


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    up = tmp_path / "uploads"
    monkeypatch.setattr(attach, "UPLOAD_DIR", up)
    return up


def test_odt_mit_leerzeichen_tab_und_ohne_fussnote(tmp_path):
    body = ('<office:text><text:h>Titel</text:h>'
            '<text:p>a<text:s text:c="3"/>b<text:tab/>c<text:span> d</text:span>'
            '<text:note><text:note-body><text:p>Fußnote</text:p></text:note-body></text:note></text:p>'
            '</office:text>')
    f = zip_mit(tmp_path / "x.odt", {"content.xml": ODF.format(body)})
    assert office_text.text_of(f) == "Titel\na   b\tc d"


def test_ods_wiederholte_leere_zeilen_und_spalten_blaehen_nicht_auf(tmp_path):
    zelle = '<table:table-cell><text:p>{}</text:p></table:table-cell>'
    body = ('<office:spreadsheet><table:table table:name="Blatt1">'
            f'<table:table-row>{zelle.format("A")}'
            '<table:table-cell table:number-columns-repeated="2"/>'
            f'{zelle.format("D")}<table:table-cell table:number-columns-repeated="16000"/>'
            '</table:table-row>'
            '<table:table-row table:number-rows-repeated="1048000">'
            '<table:table-cell table:number-columns-repeated="1024"/></table:table-row>'
            '</table:table></office:spreadsheet>')
    f = zip_mit(tmp_path / "x.ods", {"content.xml": ODF.format(body)})
    assert office_text.text_of(f) == "### Blatt1\nA\t\t\tD"


def test_docx_ohne_tabstopp_definitionen_und_mit_tabelle(tmp_path):
    doc = (f'<w:document {W}><w:body>'
           '<w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="720"/></w:tabs></w:pPr>'
           '<w:r><w:t>Hallo</w:t><w:tab/><w:t>Welt</w:t></w:r>'
           '<w:r><w:delText>weg</w:delText></w:r></w:p>'
           '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>x</w:t></w:r></w:p></w:tc>'
           '<w:tc><w:p><w:r><w:t>y</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
           '</w:body></w:document>')
    f = zip_mit(tmp_path / "x.docx", {"word/document.xml": doc})
    assert office_text.text_of(f) == "Hallo\tWelt\nx\ty"


def test_xlsx_mit_geteilten_texten_und_luecke(tmp_path):
    f = zip_mit(tmp_path / "x.xlsx", {
        "xl/workbook.xml": f'<workbook {S} {R}><sheets><sheet name="Kasse" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels":
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml": f'<sst {S}><si><t>Name</t></si><si><r><t>Ke</t></r><r><t>vin</t></r></si></sst>',
        "xl/worksheets/sheet1.xml":
            f'<worksheet {S}><sheetData>'
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1"><v>41</v></c></row>'
            '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2" t="b"><v>1</v></c></row>'
            '</sheetData></worksheet>',
    })
    assert office_text.text_of(f) == "### Kasse\nName\t\t41\nKevin\tTRUE"


def test_kaputte_datei_gibt_leeren_text(tmp_path):
    (tmp_path / "x.odt").write_bytes(b"kein zip")
    assert office_text.text_of(tmp_path / "x.odt") == ""


def test_jede_datei_ist_erlaubt_office_bekommt_auszug(uploads, tmp_path):
    odt = zip_mit(tmp_path / "brief.odt",
                  {"content.xml": ODF.format("<office:text><text:p>Hallo</text:p></office:text>")})
    r = attach.store(odt.read_bytes(), ".ODT", "brief.odt")
    assert r["kind"] == "file" and r["name"] == "brief.odt" and r["url"].endswith(".odt")
    assert (uploads / (r["url"].rsplit("/", 1)[1] + ".txt")).read_text() == "Hallo"

    r = attach.store(b"print(1)", ".py", "x.py")
    assert r["kind"] == "file"
    assert not (uploads / (r["url"].rsplit("/", 1)[1] + ".txt")).exists()


def test_seltsame_endung_kommt_nicht_in_den_dateinamen(uploads):
    r = attach.store(b"x", ".<b>", "x.<b>")
    assert r["url"].rsplit("/", 1)[1].isalnum()


def test_upload_ohne_endung(client, uploads):
    r = client.post("/api/upload", files={"file": ("README", b"hallo", "application/octet-stream")})
    assert r.status_code == 200 and r.json()["kind"] == "file"


def test_auszug_ist_kein_eigener_anhang(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "UPLOAD_DIR", tmp_path)
    for n in ("a.odt", "a.odt.txt", "b.txt", "c.pdf", "c.pdf.txt"):
        (tmp_path / n).write_text("x")
    assert sorted(gc._upload_names()) == ["a.odt", "b.txt", "c.pdf"]


def test_prompt_trennt_bilder_von_dateien(tmp_path, monkeypatch):
    monkeypatch.setattr(runs.cfg, "lang", lambda: "en")
    bild, doc, roh = tmp_path / "a.jpg", tmp_path / "b.odt", tmp_path / "c.stl"
    (tmp_path / "b.odt.txt").write_text("auszug")
    zeilen = runs.build_prompt("schau", [str(bild), str(doc), str(roh)]).splitlines()
    assert f"[Image uploaded by the user: {bild}]" in zeilen
    assert f"[File uploaded by the user: {doc} — text extract: {doc}.txt]" in zeilen
    assert f"[File uploaded by the user: {roh}]" in zeilen


def test_uploads_laufen_in_der_sandbox_ausser_pdf(client, monkeypatch, tmp_path):
    import app as appmod
    up = tmp_path / "up"
    up.mkdir()
    (up / "x.html").write_text("<script>alert(1)</script>")
    (up / "y.pdf").write_bytes(b"%PDF-1.4")
    mount = next(r for r in appmod.app.routes if getattr(r, "path", "") == "/uploads")
    monkeypatch.setattr(mount.app, "directory", str(up))
    monkeypatch.setattr(mount.app, "all_directories", [str(up)])
    r = client.get("/uploads/x.html")
    assert r.headers["content-security-policy"] == "sandbox"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in client.get("/uploads/y.pdf").headers
