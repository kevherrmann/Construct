"""Termine und Zahlen an der Nachricht statt im Systemprompt (core.lage_anhang).

Ein Systemprompt, der sich ändert, lässt Claude den ganzen Verlauf neu in den
Zwischenspeicher schreiben — bei einem neuen Termin einmal über 500.000 Tokens."""
import cal
from server import core
from server.team.chat import ohne_meldung


def _lage(monkeypatch, text):
    monkeypatch.setattr(cal, "lage_block", lambda *a, **kw: text)
    monkeypatch.setattr(core, "_dokumente_an", lambda: False)


def test_chat_persona_ohne_termine_aber_mit_anleitung(monkeypatch):
    _lage(monkeypatch, "## Dein Kalender\n- morgen: Zahnarzt")
    chat = core.load_persona(lage=False)
    assert "Zahnarzt" not in chat and "cal.py" in chat
    # Telegram und geplante Aufgaben bekommen weiter alles in einem Stück.
    assert "Zahnarzt" in core.load_persona()


def test_lage_nur_wenn_neu_oder_geaendert(monkeypatch):
    core._LAGE_GESENDET.clear()
    _lage(monkeypatch, "## Dein Kalender\n- morgen: Zahnarzt")
    erst = core.lage_anhang("s1")
    assert "Zahnarzt" in erst and erst.startswith("\n\n[")
    assert core.lage_anhang("s1") == ""
    # Neue Session (noch keine ID): immer.
    assert core.lage_anhang(None) and core.lage_anhang(None)
    # Nach dem Bearbeiten (abgezweigter Verlauf): immer.
    assert core.lage_anhang("s1", immer=True)
    _lage(monkeypatch, "## Dein Kalender\n- morgen: Zahnarzt\n- Fr: Friseur")
    assert "Friseur" in core.lage_anhang("s1")
    assert core.lage_anhang("s1") == ""


def test_lage_kommt_nach_stunden_wieder(monkeypatch):
    core._LAGE_GESENDET.clear()
    _lage(monkeypatch, "## Dein Kalender")
    assert core.lage_anhang("s2")
    h, t = core._LAGE_GESENDET["s2"]
    core._LAGE_GESENDET["s2"] = (h, t - core.LAGE_AUFFRISCHEN_S - 1)
    assert core.lage_anhang("s2")


def test_anzeige_schneidet_die_lage_ab(monkeypatch):
    core._LAGE_GESENDET.clear()
    _lage(monkeypatch, "## Dein Kalender (heute ist Mi)\n- [x] seltsam: Termin]")
    text = "Was steht an?" + core.lage_anhang("s3")
    assert ohne_meldung(text) == "Was steht an?"
    # Mit Firmenmeldung davor fällt beides weg.
    assert ohne_meldung("Und?\n\n[Firma: erledigt]" + core.lage_anhang("s3", immer=True)) == "Und?"


def test_chat_route_haengt_die_lage_einmal_an(monkeypatch, client):
    from server.routes import chat as chatroute
    core._LAGE_GESENDET.clear()
    _lage(monkeypatch, "## Dein Kalender\n- morgen: Zahnarzt")
    prompts = []

    class Lauf:
        id = "r-lage"
    monkeypatch.setattr(chatroute, "start_run", lambda prompt, *a, **kw: prompts.append(prompt) or Lauf())
    sid = "0b5e3c1a-1111-4222-8333-444455556666"
    for _ in range(2):
        assert client.post("/api/chat", json={"message": "Hallo", "session_id": sid}).status_code == 200
    assert "Zahnarzt" in prompts[0] and prompts[1] == "Hallo"
