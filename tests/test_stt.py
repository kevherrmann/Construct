"""Spracheingabe live: Nachrichten der Gemini-Live-API deuten (server/stt.py)."""
from server import stt


def test_vorlaeufig_und_final_auslesen():
    assert stt.transcripts({"serverContent": {"interimInputTranscription": {"text": "Hallo"}}}) \
        == ("Hallo", None)
    assert stt.transcripts({"serverContent": {"inputTranscription": {"text": "Hallo Cody."}}}) \
        == (None, "Hallo Cody.")
    assert stt.transcripts({"serverContent": {}, "voiceActivity": {"type": "ACTIVITY_END"}}) \
        == (None, None)
    assert stt.transcripts({"setupComplete": {}}) == (None, None)


def test_sprache_der_oberflaeche_als_hinweis():
    cfg = stt.setup_message("en")["setup"]
    assert cfg["model"] == "models/gemini-3.5-transcribe-live"
    assert cfg["inputAudioTranscription"] == {"languageCodes": ["en-US"], "mode": "SMART"}
    assert stt.setup_message("xx")["setup"]["inputAudioTranscription"]["languageCodes"] == ["de-DE"]


def test_abbruchgruende_verstaendlich():
    assert "Kontingent" in stt.close_error(1011, "Resource has been exhausted (e.g. check quota).")
    assert "Key ungültig" in stt.close_error(1007, "API key not valid. Please pass a valid API key.")
    assert stt.close_error(1011, "Internal error") == "Gemini Transcribe: Internal error (1011)"
