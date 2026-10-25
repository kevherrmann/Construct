"""Dokumente-Ablage: Erkennen, Lernen, Ablegen, Suchen, API (server/dokumente/)."""
import json
import shutil
from datetime import date

import pytest
from PIL import Image, ImageDraw, ImageFont

from server.dokumente import ablage, erkennen, ocr, scanner


def pdf_mit_text(pfad, zeilen):
    """Kleinstes PDF mit echter Textschicht (ohne Bibliothek, wie aus einem Drucker)."""
    inhalt = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(
        "(" + z.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '" for z in zeilen) + " ET"
    stream = inhalt.encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    lagen = []
    for i, o in enumerate(objs, 1):
        lagen.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{p:010d} 00000 n \n".encode() for p in lagen)
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    pfad.write_bytes(bytes(out))
    return pfad


@pytest.fixture(autouse=True)
def daten(tmp_path, monkeypatch):
    from server import config as cfg
    monkeypatch.setattr(ablage, "DATEN", tmp_path / "dokumente")
    monkeypatch.setattr(ablage, "HINTERGRUND", False)
    # Schnell und überall gleich: ohne Texterkennung (die digitalen Test-PDFs haben Text)
    monkeypatch.setattr(ocr, "verfuegbar", lambda: False)
    (tmp_path / "settings.json").write_text(json.dumps({"lang": "de", "tiles": {"dokumente": True}}))
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")
    yield tmp_path


def aufnehmen(tmp_path, name, zeilen, **kw):
    d = ablage.neu(pdf_mit_text(tmp_path / f"{name}.pdf", zeilen), titel=name, **kw)
    ablage.jetzt_lesen_alle()
    return ablage.dokument(d["id"])


# ---------- Datum ----------

def test_datum_erstes_im_kopf():
    t = "Finanzamt Ibbenbüren 23.01.2023\nFällig am 18.11.2024\nZeitraum 01.01.2022"
    assert erkennen.datum(t, date(2026, 10, 24)) == "2023-01-23"


def test_datum_ausgeschrieben_und_kurz():
    assert erkennen.datum("Mettingen, 24. Oktober 2024", date(2026, 1, 1)) == "2024-10-24"
    assert erkennen.datum("Lengerich, den 4.9.23", date(2026, 1, 1)) == "2023-09-04"


def test_datum_zukunft_und_unsinn_zaehlen_nicht():
    t = "Zahlbar bis 30.12.2099. Aktenzeichen 32.13.2020. Datum 10.09.2021"
    assert erkennen.datum(t, date(2026, 10, 24)) == "2021-09-10"
    assert erkennen.datum("kein Datum hier", date(2026, 1, 1)) is None


def test_datum_ort_und_datum_schlaegt_zinsbeginn():
    t = "Anschlusszinsvereinbarung\nAb 01.01.2019 ist das Darlehen zu verzinsen.\n" + "x " * 2000 + \
        "\nOrt, Datum\nLengerich, 13.04.2017\nUnterschrift"
    assert erkennen.datum(t, date(2026, 10, 24)) == "2017-04-13"
    assert erkennen.datum("Mettingen, den 4. Oktober 2024\nBescheid", date(2026, 1, 1)) == "2024-10-04"


def test_titelvorschlag():
    assert erkennen.titel("Ust-IDNr. DE125501924Anschlusszinsvereinbarung\n(Ergänzung des "
                          "Immobiliar-Verbraucherdarlehensvertrags)") == "Anschlusszinsvereinbarung"
    assert erkennen.titel("Finanzamt\nEinkommensteuerbescheid für 2022\n") == "Einkommensteuerbescheid 2022"
    assert erkennen.titel("GEBÜHRENRECHNUNG\nRechnungsnummer") == "Gebührenrechnung"
    assert erkennen.titel("die Steuerbescheide wurden erteilt") is None


# ---------- Ablage ----------

def test_neu_lesen_ablegen(daten):
    d = aufnehmen(daten, "Brief", ["Stadtwerke Lengerich", "Lengerich, 15.01.2026", "Jahresabrechnung Strom"])
    assert d["zustand"] == "fertig" and d["eingang"] is True
    assert "Jahresabrechnung" in d["text"] and d["seiten"] == 1
    assert d["datum"] == "2026-01-15"
    assert d["datei"] == "dateien/2026/ohne Absender/2026-01-15 Brief.pdf"
    assert (ablage.DATEN / d["datei"]).is_file()
    assert not list((ablage.DATEN / "verarbeitung").iterdir())


def test_aendern_benennt_datei_und_legt_namen_an(daten):
    d = aufnehmen(daten, "Brief", ["Rechnung", "02.03.2020"])
    neu = ablage.aendern(d["id"], {"titel": "Rechnung Steuererklärung 2018", "absender": "Steuerkanzlei Heeke",
                                   "typ": "Rechnung", "tags": ["Steuer"], "eingang": False})
    assert neu["absender"] == "Steuerkanzlei Heeke" and neu["typ"] == "Rechnung"
    assert [t["name"] for t in neu["tags"]] == ["Steuer"] and neu["eingang"] is False
    assert neu["datei"] == "dateien/2020/Steuerkanzlei Heeke/2020-03-02 Rechnung Steuererklärung 2018.pdf"
    assert (ablage.DATEN / neu["datei"]).is_file()
    # alter Ordner ist leer und weg
    assert not (ablage.DATEN / "dateien" / "2020" / "ohne Absender").exists()


def test_ungenutzte_namen_raeumen_sich_weg(daten):
    d = aufnehmen(daten, "Brief", ["Text"])
    ablage.aendern(d["id"], {"absender": "Tippfehlr", "tags": ["a"]})
    ablage.aendern(d["id"], {"absender": "Tippfehler", "tags": []})
    assert [n["name"] for n in ablage.namen("absender")] == ["Tippfehler"]
    assert ablage.namen("tags") == []


def test_gleicher_titel_ueberschreibt_nicht(daten):
    a = aufnehmen(daten, "A", ["eins", "01.02.2020"])
    b = aufnehmen(daten, "B", ["zwei", "01.02.2020"])
    ablage.aendern(a["id"], {"titel": "Gleich"})
    nb = ablage.aendern(b["id"], {"titel": "Gleich"})
    assert nb["datei"].endswith("Gleich (2).pdf")
    assert (ablage.DATEN / ablage.dokument(a["id"])["datei"]).is_file()


def test_suche_findet_inhalt_titel_absender(daten):
    d = aufnehmen(daten, "Brief", ["Grundsteuermessbescheid", "Bahnhofstraße 76", "23.01.2023"])
    ablage.aendern(d["id"], {"absender": "Finanzamt Ibbenbüren"})
    aufnehmen(daten, "Anderes", ["Rundfunkbeitrag"])
    assert [x["id"] for x in ablage.liste(q="grundsteuer")["dokumente"]] == [d["id"]]
    assert [x["id"] for x in ablage.liste(q="ibbenburen")["dokumente"]] == [d["id"]]   # ohne Umlaut
    assert [x["id"] for x in ablage.liste(q="bahnhofstr 76")["dokumente"]] == [d["id"]]
    assert ablage.liste(q='"; DROP TABLE dokumente; --')["gesamt"] == 0          # keine FTS-Syntax
    assert ablage.liste(jahr="2023")["gesamt"] == 1


def test_scan_titel_wird_ersetzt_echter_nicht(daten):
    a = ablage.neu(pdf_mit_text(daten / "a.pdf", ["Kontoauszug 2023", "Sparkasse"]), titel="Scan 24.10.2026 23:43")
    b = ablage.neu(pdf_mit_text(daten / "b.pdf", ["Kontoauszug 2023"]), titel="Mein Titel")
    c = ablage.neu(pdf_mit_text(daten / "c.pdf", ["Kontoauszug"]), titel="Scan 24.10.2026 23:43 (Teil 2)")
    ablage.jetzt_lesen_alle()
    assert ablage.dokument(a["id"])["titel"] == "Kontoauszug 2023"
    assert ablage.dokument(b["id"])["titel"] == "Mein Titel"
    assert ablage.dokument(c["id"])["titel"] == "Kontoauszug (Teil 2)"


def test_nummern_werden_nicht_wiederverwendet(daten):
    a = aufnehmen(daten, "A", ["eins"])
    ablage.loeschen(a["id"])
    b = aufnehmen(daten, "B", ["zwei"])
    assert b["id"] == a["id"] + 1


def test_loeschen_legt_in_papierkorb(daten):
    d = aufnehmen(daten, "Weg", ["x"])
    ablage.loeschen(d["id"])
    with pytest.raises(KeyError):
        ablage.dokument(d["id"])
    assert len(list((ablage.DATEN / "papierkorb").iterdir())) == 1
    assert ablage.liste(q="Weg")["gesamt"] == 0


def test_doppelte_datei_bekommt_hinweis(daten):
    a = aufnehmen(daten, "A", ["gleich"])
    b = aufnehmen(daten, "A", ["gleich"])
    assert b["hinweis"] == f"gleiche Datei wie Dokument {a['id']}"


def test_zweiter_leser_wartet_auf_sperre(daten):
    import os
    d = ablage.neu(pdf_mit_text(daten / "x.pdf", ["Text"]), titel="x")
    sperre = ablage.DATEN / "verarbeitung" / f"{d['id']}.sperre"
    sperre.write_text(str(os.getpid()))           # ein lebender Prozess liest gerade
    ablage.lesen(d["id"])
    assert ablage.dokument(d["id"])["zustand"] == "lesen"
    sperre.write_text("999999999")               # Absturz: Prozess gibt es nicht mehr
    ablage.lesen(d["id"])
    assert ablage.dokument(d["id"])["zustand"] == "fertig" and not sperre.exists()


def test_teilen(daten):
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for i in range(1, 5):
        w.append(str(pdf_mit_text(daten / f"s{i}.pdf", [f"Seite {i}"])))
    with open(daten / "vier.pdf", "wb") as f:
        w.write(f)
    d = ablage.neu(daten / "vier.pdf", titel="Stapel")
    ablage.jetzt_lesen_alle()
    ablage.aendern(d["id"], {"absender": "Sparkasse", "tags": ["Haus"]})
    with pytest.raises(ablage.Fehler):
        ablage.teilen(d["id"], "1-2, 2-3")
    with pytest.raises(ablage.Fehler):
        ablage.teilen(d["id"], "1-9")
    teile = ablage.teilen(d["id"], "1-2, 4")
    ablage.jetzt_lesen_alle()
    a, b = (ablage.dokument(x["id"]) for x in teile)
    assert (a["seiten"], b["seiten"]) == (2, 1)
    assert "Seite 4" in b["text"] and a["absender"] == "Sparkasse" and b["tags"][0]["name"] == "Haus"
    assert a["titel"] == "Stapel (Teil 1)"
    with pytest.raises(KeyError):
        ablage.dokument(d["id"])
    assert len(PdfReader(str(next((ablage.DATEN / "papierkorb").iterdir()))).pages) == 4


def test_zusammenfuegen(daten):
    a = aufnehmen(daten, "Brief", ["Seite 1 von 2", "Lengerich, 09.05.2023"])
    b = aufnehmen(daten, "Rest", ["Seite 2 von 2"])
    ablage.aendern(a["id"], {"absender": "Provinzial", "tags": ["Versicherung"]})
    ablage.aendern(b["id"], {"tags": ["Rente"]})
    with pytest.raises(ablage.Fehler):
        ablage.zusammenfuegen([a["id"]])
    neu = ablage.zusammenfuegen([a["id"], b["id"]])
    ablage.jetzt_lesen_alle()
    d = ablage.dokument(neu["id"])
    assert d["seiten"] == 2 and d["text"].index("Seite 1") < d["text"].index("Seite 2")
    assert d["absender"] == "Provinzial" and d["datum"] == "2023-05-09" and d["titel"] == "Brief"
    assert {g["name"] for g in d["tags"]} == {"Versicherung", "Rente"}
    for i in (a["id"], b["id"]):
        with pytest.raises(KeyError):
            ablage.dokument(i)


# ---------- Lernen ----------

def test_lernt_nur_aus_bestaetigten(daten):
    for i in range(3):
        d = aufnehmen(daten, f"fa{i}", ["Finanzamt Ibbenbüren", "Einkommensteuerbescheid", f"Steuernummer 327 {i}"])
        ablage.aendern(d["id"], {"absender": "Finanzamt Ibbenbüren", "typ": "Bescheid", "tags": ["Steuer"],
                                 "eingang": False})
    for i in range(3):
        d = aufnehmen(daten, f"sk{i}", ["Sparkasse", "Kontoauszug Girokonto", f"Saldo {i}"])
        ablage.aendern(d["id"], {"absender": "Sparkasse", "typ": "Kontoauszug", "eingang": False})
    # unbestätigter Irrtum im Eingang darf nichts beibringen
    falsch = aufnehmen(daten, "irrtum", ["Einkommensteuerbescheid Steuernummer"])
    ablage.aendern(falsch["id"], {"absender": "Sparkasse"})

    neu = aufnehmen(daten, "neu", ["Einkommensteuerbescheid für 2021", "Steuernummer 327"])
    assert neu["absender"] == "Finanzamt Ibbenbüren"   # gelernt: der Name steht nicht im Text
    assert neu["typ"] == "Bescheid"
    assert [t["name"] for t in neu["tags"]] == ["Steuer"]
    giro = aufnehmen(daten, "giro", ["Kontoauszug Girokonto Saldo"])
    assert giro["typ"] == "Kontoauszug" and giro["tags"] == []


def test_bescheid_an_steuerberater_bleibt_finanzamt(daten):
    # Steuerberater-Post klingt nach Steuer, der Bescheid nennt aber das Finanzamt wörtlich
    for i in range(3):
        d = aufnehmen(daten, f"sb{i}", ["Steuerkanzlei Heeke", "Einkommensteuer Bescheid geprüft", str(i)])
        ablage.aendern(d["id"], {"absender": "Steuerkanzlei Heeke", "eingang": False})
    d = aufnehmen(daten, "fa", ["Finanzamt Ibbenbüren", "Steuerberater"])
    ablage.aendern(d["id"], {"absender": "Finanzamt Ibbenbüren", "eingang": False})
    neu = aufnehmen(daten, "bescheid", ["Finanzamt Ibbenbüren", "Einkommensteuer Bescheid", "Herrn Steuerberater"])
    assert neu["absender"] == "Finanzamt Ibbenbüren"


def test_unbekannter_absender_bekommt_keinen_falschen_vorschlag(daten):
    # Versicherungspost, die die Sparkasse als Betreuerin im Kopf nennt, ist kein Darlehen
    for i in range(3):
        d = aufnehmen(daten, f"dl{i}", ["Stadtsparkasse Lengerich Bahnhofstr. 76", "Darlehensvertrag Sollzins Tilgung",
                                        f"Darlehen 6016{i} Annuität Restschuld Grundschuld Zinsbindung",
                                        "Vorfälligkeitsentschädigung Sondertilgung Effektivzins Nennbetrag",
                                        "Widerrufsinformation Darlehensnehmer Auszahlung Bereitstellungszinsen"])
        ablage.aendern(d["id"], {"absender": "Stadtsparkasse Lengerich", "typ": "Vertrag",
                                 "tags": ["Darlehen", "Original aufheben"], "eingang": False})
    for i in range(3):
        d = aufnehmen(daten, f"fa{i}", ["Finanzamt Ibbenbüren", f"Einkommensteuerbescheid 20{i}"])
        ablage.aendern(d["id"], {"absender": "Finanzamt Ibbenbüren", "typ": "Bescheid", "eingang": False})
    neu = aufnehmen(daten, "prov", ["PROVINZIAL Es betreut Sie Stadtsparkasse Lengerich Bahnhofstr. 76",
                                    "Lastschriftmitteilung Haftpflichtversicherung Beitrag 8,16",
                                    "Versicherungsnummer Beitragsrechnung Lastschrift Fälligkeit Versicherungsschutz",
                                    "Privathaftpflicht Rundumschutz Versicherungsjahr Beitragszahlung Kundenservice"])
    assert neu["absender"] is None and neu["typ"] is None and neu["tags"] == []


def test_vorschlag_ueberschreibt_nichts_gesetztes(daten):
    for i in range(2):
        d = aufnehmen(daten, f"x{i}", ["Sparkasse Kontoauszug"])
        ablage.aendern(d["id"], {"absender": "Sparkasse", "eingang": False})
    d = ablage.neu(pdf_mit_text(daten / "n.pdf", ["Sparkasse Kontoauszug"]), titel="n")
    ablage.aendern(d["id"], {"absender": "Andere Bank"})      # vor dem Lesen schon gesetzt
    ablage.jetzt_lesen_alle()
    assert ablage.dokument(d["id"])["absender"] == "Andere Bank"


# ---------- Scanner (ohne Gerät) ----------

def test_leere_rueckseite_mit_bleistiftnotiz_bleibt():
    leer_ = Image.new("L", (2480, 3508), 255)
    d = ImageDraw.Draw(leer_)
    for y in range(400, 3000, 60):                       # durchscheinender Text von vorn
        d.text((250, y), "Durchscheinender Text " * 4, fill=205, font=ImageFont.load_default(40))
    assert scanner.leer(leer_)
    notiz = leer_.copy()
    ImageDraw.Draw(notiz).text((1300, 150), "Hinten Seite 1", fill=80, font=ImageFont.load_default(110))
    assert not scanner.leer(notiz)


def test_sitzung_ordnet_gewendete_rueckseiten_zu(daten, monkeypatch):
    s = scanner.Sitzung({"id": "x", "name": "Test", "ip": ""}, farbe=False)
    font = ImageFont.load_default(120)

    def blatt(ordner, n, txt):
        b = Image.new("L", (1240, 1754), 255)
        ImageDraw.Draw(b).text((100, 100), txt, fill=0, font=font)
        b.save(s.ordner / ordner / f"s{n:03d}.jpg")
    blatt("vorne", 1, "Vorne 1")
    blatt("vorne", 2, "Vorne 2")
    blatt("vorne", 3, "Vorne 3")
    # gewendet: Blatt 3 zuerst, Blatt 2 hinten leer
    blatt("hinten", 1, "Hinten 3")
    Image.new("L", (1240, 1754), 255).save(s.ordner / "hinten" / "s002.jpg")
    blatt("hinten", 3, "Hinten 1")
    neu = s.fertig(einzeln=True)
    ablage.jetzt_lesen_alle()
    seiten = [ablage.dokument(d["id"])["seiten"] for d in neu]
    assert seiten == [2, 1, 2]
    assert not s.ordner.exists()


def test_sitzung_einzelne_rueckseite_von_hand_zugeordnet(daten):
    # Nur das eine Blatt mit Rückseite wurde gewendet: Zuordnung kommt vom Nutzer
    s = scanner.Sitzung({"id": "x", "name": "Test", "ip": ""}, farbe=False)
    font = ImageFont.load_default(120)
    for ordner, n, txt in (("vorne", 1, "V1"), ("vorne", 2, "V2"), ("vorne", 3, "V3"), ("hinten", 1, "R2")):
        b = Image.new("L", (1240, 1754), 255)
        ImageDraw.Draw(b).text((100, 100), txt * 5, fill=0, font=font)
        b.save(s.ordner / ordner / f"s{n:03d}.jpg")
    neu = s.fertig(einzeln=True, zuordnung=[2])
    ablage.jetzt_lesen_alle()
    assert [ablage.dokument(d["id"])["seiten"] for d in neu] == [1, 2, 1]
    s2 = scanner.Sitzung({"id": "x", "name": "Test", "ip": ""}, farbe=False)
    Image.new("L", (600, 800), 255).save(s2.ordner / "vorne" / "s001.jpg")
    Image.new("L", (600, 800), 255).save(s2.ordner / "hinten" / "s001.jpg")
    with pytest.raises(ablage.Fehler):
        s2.fertig(einzeln=False, zuordnung=[1, 1])


def test_sitzung_ungleiche_rueckseiten_werden_nicht_geraten(daten):
    s = scanner.Sitzung({"id": "x", "name": "Test", "ip": ""}, farbe=False)
    for ordner, n in (("vorne", 1), ("vorne", 2), ("hinten", 1)):
        Image.new("L", (600, 800), 255).save(s.ordner / ordner / f"s{n:03d}.jpg")
    neu = s.fertig(einzeln=False)
    assert len(neu) == 2 and "Rückseiten, bitte prüfen" in neu[1]["titel"]


# ---------- Texterkennung echt (nur wenn installiert) ----------

@pytest.mark.skipif(shutil.which("ocrmypdf") is None, reason="OCRmyPDF nicht installiert")
def test_texterkennung_dreht_kopfstehende_seite(daten, monkeypatch):
    monkeypatch.setattr(ocr, "verfuegbar", lambda: True)
    b = Image.new("L", (1240, 1754), 255)
    font = ImageFont.load_default(44)
    for i, z in enumerate(["Finanzamt Ibbenbüren", "Bescheid über Einkommensteuer",
                           "Ibbenbüren, den 23.01.2023", "Sehr geehrter Herr Herrmann,",
                           "die Steuer wird festgesetzt auf 1.234,00 Euro."] * 3):
        ImageDraw.Draw(b).text((100, 120 + i * 70), z, fill=0, font=font)
    pdf = daten / "kopf.pdf"
    ocr.bilder_zu_pdf([b.rotate(180)], pdf, 150)
    d = ablage.neu(pdf, titel="kopf")
    ablage.jetzt_lesen_alle()
    d = ablage.dokument(d["id"])
    assert "Einkommensteuer" in d["text"] and d["datum"] == "2023-01-23"


# ---------- API ----------

def test_api_aus_wenn_kachel_aus(client, daten):
    (daten / "settings.json").write_text(json.dumps({"tiles": {"dokumente": False}}))
    assert client.get("/api/dokumente/uebersicht").status_code == 404


def test_api_hochladen_liste_aendern_datei(client, daten):
    pdf = pdf_mit_text(daten / "up.pdf", ["Rundfunkbeitrag", "Datum 10.09.2021"])
    r = client.post("/api/dokumente/hochladen", files={"datei": ("Beitrag.pdf", pdf.read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    id_ = r.json()["id"]
    ablage.jetzt_lesen_alle()
    assert client.get("/api/dokumente/uebersicht").json()["eingang"] == 1
    assert client.get("/api/dokumente", params={"q": "rundfunk"}).json()["gesamt"] == 1
    r = client.post(f"/api/dokumente/{id_}", json={"absender": "ARD ZDF Beitragsservice", "eingang": False})
    assert r.json()["absender"] == "ARD ZDF Beitragsservice"
    f = client.get(f"/api/dokumente/{id_}/datei")
    assert f.status_code == 200 and f.content.startswith(b"%PDF")
    assert client.post("/api/dokumente/hochladen",
                       files={"datei": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert client.get("/api/dokumente/9999").status_code == 404


def test_api_foto_wird_pdf(client, daten):
    import io
    buf = io.BytesIO()
    Image.new("RGB", (800, 1100), "white").save(buf, "JPEG")
    r = client.post("/api/dokumente/hochladen", files={"datei": ("Handy.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 200
    ablage.jetzt_lesen_alle()
    assert ablage.datei(r.json()["id"]).read_bytes().startswith(b"%PDF")


def test_kontext_nur_mit_kachel(daten):
    from server import core
    assert "Dokumente-Ablage" in core.dokumente_text()
    (daten / "settings.json").write_text(json.dumps({"tiles": {"dokumente": False}}))
    assert core.dokumente_text() == ""


def test_cli_set_und_search(daten, capsys):
    import doku
    d = aufnehmen(daten, "Brief", ["Zensus 2022", "27.05.2022"])
    assert doku.main(["set", str(d["id"]), "--sender", "IT.NRW", "--tags", "Haus, Steuer", "--done"]) == 0
    assert doku.main(["search", "zensus"]) == 0
    out = capsys.readouterr().out
    assert "IT.NRW" in out and "1 Treffer" in out and "[Haus,Steuer]" in out
