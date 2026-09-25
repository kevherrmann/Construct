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
    monkeypatch.setattr(core, "calendar_text", lambda: "## Dein Kalender\n- Mo: Zahnarzt")
    sent = hermes.with_context("Was steht an?")
    assert "Zahnarzt" in sent and sent.startswith("Was steht an?")
    assert hermes.strip_context(sent) == "Was steht an?"
    assert hermes.strip_context("Ohne Kontext") == "Ohne Kontext"
    monkeypatch.setattr(core, "calendar_text", lambda: "")
    assert hermes.with_context("Hallo") == "Hallo"
