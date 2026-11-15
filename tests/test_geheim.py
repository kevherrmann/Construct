"""Geheimnis-Dateien nur für das eigene Konto (server/geheim.py)."""
from conftest import nur_fuer_mich_lesbar

from server.geheim import nur_fuer_mich


def test_datei_ist_danach_nur_fuer_mich(tmp_path):
    p = tmp_path / "schluessel.json"
    p.write_text('{"key": "sk-geheim"}', encoding="utf-8")
    p.chmod(0o644)
    assert not nur_fuer_mich_lesbar(p)       # vorher: auch für andere lesbar
    nur_fuer_mich(p)
    assert nur_fuer_mich_lesbar(p)
    # Lesen und überschreiben muss der Besitzer weiterhin können
    p.write_text('{"key": "sk-neu"}', encoding="utf-8")
    assert "sk-neu" in p.read_text(encoding="utf-8")


def test_rechte_ueberleben_das_atomare_ersetzen(tmp_path):
    # So speichern llm.py, mail.py & Co.: tmp schreiben, abschließen, umbenennen
    ziel = tmp_path / "konto.json"
    ziel.write_text("alt", encoding="utf-8")
    tmp = ziel.with_suffix(".json.tmp")
    tmp.write_text("neu", encoding="utf-8")
    nur_fuer_mich(tmp)
    tmp.replace(ziel)
    assert nur_fuer_mich_lesbar(ziel) and ziel.read_text(encoding="utf-8") == "neu"
