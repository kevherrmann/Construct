"""Transkripte lesen und Modell-IDs zurückführen (server/sessions.py)."""
import json

from server.sessions import _last_model, _parse_transcript_lines, model_short


def jl(*events):
    return "\n".join(json.dumps(e) for e in events).encode()


def test_model_short_behaelt_volle_id_ohne_zusaetze():
    assert model_short("claude-opus-5-5") == "claude-opus-5-5"
    assert model_short("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    assert model_short("claude-opus-5-5[1m]") == "claude-opus-5-5"
    assert model_short("<synthetic>") == ""
    assert model_short("") == ""


def test_transkript_zeigt_nur_echte_nachrichten():
    data = jl(
        {"type": "user", "message": {"content": "Hallo"}},
        {"type": "user", "message": {"content": "<system-reminder>x</system-reminder>"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Moin!"}]}},
        {"type": "summary", "summary": "egal"},
    ) + b"\nkaputte zeile\n"
    assert _parse_transcript_lines(data) == [
        {"role": "user", "text": "Hallo"},
        {"role": "assistant", "text": "Moin!"},
    ]


def test_letztes_modell_der_session():
    data = jl(
        {"type": "assistant", "message": {"model": "claude-sonnet-5", "content": "a"}},
        {"type": "assistant", "message": {"model": "claude-opus-5-5[1m]", "content": "b"}},
        {"type": "user", "message": {"content": "c"}},
    )
    assert _last_model(data) == "claude-opus-5-5"


def test_nachricht_zum_bearbeiten_wiederfinden(tmp_path, monkeypatch):
    from server import sessions

    sid = "abcd1234-0000-0000-0000-000000000000"
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / f"{sid}.jsonl").write_bytes(jl(
        {"type": "user", "uuid": "u1", "parentUuid": None, "message": {"content": "Hallo"}},
        {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "message": {"content": "Moin"}},
        {"type": "user", "uuid": "u2", "parentUuid": "a1",
         "message": {"content": "Schau das an\n\n[Vom Nutzer hochgeladenes Bild: /x.png]"}},
        {"type": "assistant", "uuid": "a2", "parentUuid": "u2", "message": {"content": "Ok"}},
        {"type": "user", "uuid": "u3", "parentUuid": "a2", "message": {"content": "Hallo"}},
    ))
    monkeypatch.setattr(sessions, "PROJECTS_DIR", tmp_path)
    # erste Nachricht: kein Vorgänger → neue Sitzung
    assert sessions.find_prompt(sid, "Hallo", 0) == ("u1", None)
    # gleicher Text zum zweiten Mal
    assert sessions.find_prompt(sid, "Hallo", 1) == ("u3", "a2")
    # mit angehängtem Bild-Hinweis
    assert sessions.find_prompt(sid, "Schau das an", 0) == ("u2", "a1")
    assert sessions.find_prompt(sid, "Gibt es nicht", 0) is None
    assert sessions.find_prompt("../boese", "Hallo", 0) is None
