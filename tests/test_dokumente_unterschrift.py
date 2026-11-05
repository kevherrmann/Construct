"""Dokumente unterschreiben (server/dokumente/unterschrift.py)."""
import io

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter

from server.dokumente import ablage, unterschrift
from tests import test_dokumente as td

aufnehmen = td.aufnehmen
daten = td.daten     # Fixture: eigene Ablage je Test


def foto_einer_unterschrift() -> bytes:
    """Graues Papier mit dunkler Linie, wie vom Handy."""
    b = Image.new("RGB", (800, 400), (225, 222, 215))
    ImageDraw.Draw(b).line([(100, 250), (300, 150), (500, 260), (700, 140)], fill=(20, 30, 90), width=12)
    out = io.BytesIO()
    b.save(out, "JPEG")
    return out.getvalue()


def test_foto_wird_freigestellt_und_zugeschnitten():
    unterschrift.speichern(foto_einer_unterschrift())
    with Image.open(io.BytesIO(unterschrift.lesen())) as b:
        assert b.mode == "RGBA"
        assert b.width < 700 and b.height < 200          # Papierrand weg
        assert b.getpixel((0, 0))[3] == 0                 # Ecke durchsichtig
        assert b.getchannel("A").getextrema()[1] == 255    # Tinte deckend


def test_leeres_bild_ist_keine_unterschrift():
    out = io.BytesIO()
    Image.new("RGB", (300, 100), "white").save(out, "PNG")
    with pytest.raises(ablage.Fehler):
        unterschrift.speichern(out.getvalue())
    with pytest.raises(ablage.Fehler):
        unterschrift.speichern(b"kein bild")
    assert not unterschrift.vorhanden()


def test_unterschreiben_legt_neues_dokument_an(daten):
    d = aufnehmen(daten, "Vertrag", ["Mietvertrag", "Unterschrift Mieter"])
    ablage.aendern(d["id"], {"absender": "Vermieter", "tags": ["Wohnung"], "eingang": False})
    unterschrift.speichern(foto_einer_unterschrift())
    x = unterschrift.unterschreiben(d["id"], [
        {"art": "unterschrift", "seite": 1, "x": 0.1, "y": 0.8, "breite": 0.3},
        {"art": "text", "seite": 1, "x": 0.5, "y": 0.85, "hoehe": 0.014, "text": "Lengerich, 05.11.2026 (ü)"},
    ])
    ablage.jetzt_lesen_alle()
    x = ablage.dokument(x["id"])
    assert x["titel"] == "Vertrag (unterschrieben)"
    assert x["absender"] == "Vermieter" and [g["name"] for g in x["tags"]] == ["Wohnung"]
    assert not x["eingang"]
    assert "Lengerich, 05.11.2026 (ü)" in x["text"]          # Text ist echter, durchsuchbarer Text
    assert "Mietvertrag" in x["text"]                          # Original-Inhalt noch da
    seite = PdfReader(str(ablage.datei(x["id"]))).pages[0]
    xo = seite["/Resources"]["/XObject"]
    bild = xo["/CxUnterschrift"].get_object()
    assert "/SMask" in bild
    # Original unverändert
    assert "CxUnterschrift" not in str(PdfReader(str(ablage.datei(d["id"]))).pages[0]["/Resources"])


def test_gedrehte_seite_landet_an_der_sichtbaren_stelle(daten):
    d = aufnehmen(daten, "Quer", ["Quer"])
    # Seite um 90° drehen und neu ablegen
    w = PdfWriter(clone_from=str(ablage.datei(d["id"])))
    w.pages[0].rotate(90)
    with open(ablage.datei(d["id"]), "wb") as f:
        w.write(f)
    assert unterschrift.seiten(d["id"]) == [{"breite": 842, "hoehe": 595}]
    unterschrift.speichern(foto_einer_unterschrift())
    x = unterschrift.unterschreiben(d["id"], [{"art": "unterschrift", "seite": 1, "x": 0, "y": 0, "breite": 0.2}])
    inhalt = PdfReader(str(ablage.datei(x["id"]))).pages[0].get_contents().get_data().decode("latin-1")
    # Oben links sichtbar = bei Drehung 90 die Ecke unten links im PDF (x klein, y klein)
    zeile = [z for z in inhalt.splitlines() if "CxUnterschrift" in z][0]
    assert zeile.startswith("q 0 1 -1 0 595 0 cm")
    breite = 0.2 * 842
    hoehe = breite * Image.open(io.BytesIO(unterschrift.lesen())).height / Image.open(
        io.BytesIO(unterschrift.lesen())).width
    teile = zeile.split()
    u, v = float(teile[12]), float(teile[13])
    assert u == 0 and abs(v - (595 - hoehe)) < 0.01


def test_ohne_unterschrift_oder_unsinn_gibt_fehler(daten):
    d = aufnehmen(daten, "Brief", ["Hallo"])
    with pytest.raises(ablage.Fehler):
        unterschrift.unterschreiben(d["id"], [{"art": "unterschrift", "seite": 1, "x": 0, "y": 0, "breite": .2}])
    with pytest.raises(ablage.Fehler):
        unterschrift.unterschreiben(d["id"], [])
    with pytest.raises(ablage.Fehler):
        unterschrift.unterschreiben(d["id"], [{"art": "text", "seite": 9, "x": 0, "y": 0, "hoehe": .02, "text": "a"}])
    with pytest.raises(ablage.Fehler):
        unterschrift.unterschreiben(d["id"], ["quatsch"])
