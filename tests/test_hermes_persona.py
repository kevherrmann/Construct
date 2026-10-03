"""Persona und Kalender für fremde Modelle (server/hermes.py)."""
import pytest

from server import core
from server import hermes


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(hermes, "hermes_home", lambda: str(tmp_path))
    monkeypatch.setattr(core, "persona_text", lambda: "Ich bin Cody.")
    return tmp_path


def test_soul_wird_angelegt_und_nachgefuehrt(home, monkeypatch):
    assert hermes.sync_soul()
    soul = (home / "SOUL.md").read_text()
    assert soul.startswith(hermes.SOUL_MARK) and "Ich bin Cody." in soul
    monkeypatch.setattr(core, "persona_text", lambda: "Ich bin Cody, jetzt mit Humor.")
    assert hermes.sync_soul()
    assert "jetzt mit Humor" in (home / "SOUL.md").read_text()


def test_hermes_vorgabe_wird_ersetzt(home):
    (home / "SOUL.md").write_text(hermes.HERMES_DEFAULT_SOUL + " Be direct.")
    assert hermes.sync_soul()
    assert "Ich bin Cody." in (home / "SOUL.md").read_text()


def test_eigene_soul_bleibt_unangetastet(home):
    (home / "SOUL.md").write_text("Du bist mein Piraten-Agent.")
    assert not hermes.sync_soul()
    assert (home / "SOUL.md").read_text() == "Du bist mein Piraten-Agent."


def test_kalender_geht_mit_und_verschwindet_in_der_anzeige(monkeypatch):
    # Unabhängig davon, ob auf diesem Rechner ein fal-Key liegt (Bild-Hinweis).
    from server import images
    monkeypatch.setattr(images, "context_block", lambda: "")
    monkeypatch.setattr(core, "calendar_text", lambda: "## Dein Kalender\n- Mo: Zahnarzt")
    sent = hermes.with_context("Was steht an?")
    assert "Zahnarzt" in sent and sent.startswith("Was steht an?")
    assert hermes.strip_context(sent) == "Was steht an?"
    assert hermes.strip_context("Ohne Kontext") == "Ohne Kontext"
    monkeypatch.setattr(core, "calendar_text", lambda: "")
    assert hermes.with_context("Hallo") == "Hallo"


def test_bonsai_bekommt_seine_adresse_auch_beim_fortsetzen(monkeypatch):
    # Sonst löst Hermes den gespeicherten Anbieter "custom" beim Fortsetzen
    # nicht auf und schickt die zweite Nachricht an Gemini.
    from server import bonsai
    monkeypatch.delenv("CUSTOM_BASE_URL", raising=False)
    assert hermes.run_env("bonsai:Ternary-Bonsai-8B")["CUSTOM_BASE_URL"] == bonsai.BASE_URL
    assert "CUSTOM_BASE_URL" not in hermes.run_env("gemini:gemini-2.5-flash")


def test_lokale_modelle_bekommen_kontext_vorn_und_ohne_bilder(monkeypatch):
    from server import images
    monkeypatch.setattr(images, "context_block", lambda: "## Bilder erzeugen\n…")
    monkeypatch.setattr(core, "calendar_text", lambda: "## Dein Kalender\n- Mo: Zahnarzt")
    lokal = hermes.with_context("Sag nur: eins", lokal=True)
    assert lokal.startswith(hermes.CTX_OPEN) and lokal.endswith("Sag nur: eins")
    assert "Bilder erzeugen" not in lokal and "Zahnarzt" in lokal
    assert hermes.strip_context(lokal) == "Sag nur: eins"
    sonst = hermes.with_context("Sag nur: eins")
    assert sonst.startswith("Sag nur: eins") and "Bilder erzeugen" in sonst
    assert hermes.strip_context(sonst) == "Sag nur: eins"


def test_eigene_persona_nur_fuer_lokale_modelle(home, monkeypatch):
    monkeypatch.setattr(hermes, "lokale_persona", lambda: "Du bist ein grummeliger Pirat.")
    assert hermes.sync_soul(lokal=True)
    soul = (home / "SOUL.md").read_text()
    assert "Pirat" in soul and "Ich bin Cody." not in soul
    assert hermes.sync_soul(lokal=False)
    soul = (home / "SOUL.md").read_text()
    assert "Ich bin Cody." in soul and "Pirat" not in soul


def test_ohne_eigene_persona_gilt_auch_lokal_codys(home, monkeypatch):
    monkeypatch.setattr(hermes, "lokale_persona", lambda: "")
    assert hermes.sync_soul(lokal=True)
    assert "Ich bin Cody." in (home / "SOUL.md").read_text()


def test_persona_datei_fuer_lokale_modelle_ist_speicherbar(tmp_path, monkeypatch):
    from server import config
    monkeypatch.setitem(config.PERSONA_FILES, "lokal", (tmp_path / "SOUL.lokal.md", None))
    assert config.persona_read("lokal") == ""
    config.persona_write("lokal", "Arrr.")
    assert config.persona_read("lokal") == "Arrr."
