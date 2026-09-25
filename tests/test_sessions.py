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
