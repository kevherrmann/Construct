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


def test_alte_dateien_werden_beim_start_abgeschlossen(tmp_path, monkeypatch):
    import os
    from server import geheim
    alt = tmp_path / ".llm-config.json"
    alt.write_text("{}", encoding="utf-8")
    alt.chmod(0o644)
    fehlt = tmp_path / ".telegram.json"
    geheim.alte_abschliessen([alt, fehlt])     # fehlende Dateien stören nicht
    if os.name == "nt":
        assert nur_fuer_mich_lesbar(alt)
    else:
        # Unter Linux/macOS war chmod 600 schon immer da: nichts anfassen
        assert not nur_fuer_mich_lesbar(alt)
    assert not fehlt.exists()
