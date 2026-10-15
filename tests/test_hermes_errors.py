"""Fehlermeldungen von Hermes als kurzer Hinweis (server/hermes.py)."""
from server import config as cfg
from server import hermes

# Wortgleich aus einem echten Lauf (Gemini-Free-Tier, 2026-09-25).
GEMINI_429 = """Google AI Studio rate-limited every one of 3 attempts — it looks temporarily unavailable. Wait a minute and send /retry, or switch models with /model. To avoid this in future, add a backup provider with `hermes fallback add`.

Provider said: Gemini HTTP 429 (RESOURCE_EXHAUSTED): You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. 
* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 5, model: gemini-3.5-flash
Please retry in 47.440993984s."""


def test_limit_wird_kurzer_hinweis(monkeypatch):
    monkeypatch.setattr(cfg, "L", lambda de, en: de)
    msg = hermes.friendly_failure(GEMINI_429)
    assert msg.startswith("⚠ **Kontingent erschöpft** — Google AI Studio")
    assert "Lite-Modelle" in msg              # Free-Tier erkannt
    assert "/retry" not in msg and "hermes fallback" not in msg
    assert "_Details: Gemini HTTP 429 (RESOURCE_EXHAUSTED)" in msg


def test_andere_faelle(monkeypatch):
    monkeypatch.setattr(cfg, "L", lambda de, en: en)
    assert "resets in 3h 10m" in hermes.friendly_failure(
        "OpenAI rate-limited every one of 2 attempts — its usage limit resets in 3h 10m. "
        "Send /retry after that, or switch models with /model.")
    assert "not responding" in hermes.friendly_failure(
        "DeepSeek reported it was overloaded on all 3 attempts — it looks temporarily unavailable.")
    assert "rejected the credentials" in hermes.friendly_failure(
        "OpenAI rejected your API key, so the model can't be reached. Update it in Settings.")
    assert "'gpt-9' is not available on OpenAI" in hermes.friendly_failure(
        "Model 'gpt-9' isn't available on OpenAI. Pick a different model with /model.")
    # Free-Tier-Abbruch nach dem ersten Versuch (agent/turn_failure_copy.py,
    # _EXHAUSTED_FIRST_ATTEMPT_LEADS)
    assert "resets in 52s" in hermes.friendly_failure(
        "Google AI Studio is rate-limiting requests right now — its usage limit resets in 52s. "
        "Send /retry after that, or switch models with /model.")


def test_freigabe_nur_fuer_die_sitzung():
    # So bietet Hermes sie an (acp_adapter/permissions.py) — auch in anderer
    # Reihenfolge darf nie die dauerhafte Freigabe gewählt werden.
    opts = [{"optionId": "allow_once", "kind": "allow_once"},
            {"optionId": "allow_always", "kind": "allow_always"},
            {"optionId": "allow_session", "kind": "allow_always"},
            {"optionId": "deny", "kind": "reject_once"}]
    assert hermes._permission_choice({"options": opts}, True) == "allow_session"
    assert hermes._permission_choice({"options": opts}, False) == "deny"
    nur_einmal = [o for o in opts if o["optionId"] in ("allow_once", "deny")]
    assert hermes._permission_choice({"options": nur_einmal}, True) == "allow_once"


def test_normale_antworten_bleiben():
    assert hermes.friendly_failure("Ich heiße Cody.") is None
    assert hermes.friendly_failure("Die API ist rate-limited every one of 3 attempts, sagt man.") is None
