"""Grundlagen (server/core.py) und Einstellungen (config.py)."""
import json
import time

from server import config, core
from server.core import (BASE_DIR, LIMIT_HIT, STREAM_USAGE, VERSION, extract_text, friendly_claude_error,
                         note_rate_limit, sse)


def test_base_dir_ist_der_projektordner():
    # core.py liegt in server/ — der Projektordner ist eine Ebene höher.
    assert (BASE_DIR / "app.py").exists()


def test_version_ueberall_gleich():
    # Die Kopfzeile zeigt core.VERSION — beim Release leicht zu vergessen.
    pkg = json.loads((BASE_DIR / "frontend" / "package.json").read_text(encoding="utf-8"))
    log = (BASE_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    assert pkg["version"] == VERSION
    newest = next(line for line in log.splitlines() if line.startswith("## "))
    assert newest.startswith(f"## {VERSION} ")


def test_sse_format():
    assert sse({"type": "text", "text": "ä"}) == 'data: {"type": "text", "text": "ä"}\n\n'


def test_extract_text_aus_bloecken():
    text = extract_text([{"type": "text", "text": "a"}, {"type": "tool_use", "name": "Read"}, {"type": "text", "text": "b"}])
    assert "a" in text and "b" in text
    assert extract_text(None) == ""
    assert extract_text("x") == "x"


def test_limit_fehler_wird_erklaert_und_gemerkt():
    msg = friendly_claude_error("Claude AI usage limit reached|1790000000")
    assert msg.startswith("⛔")
    assert LIMIT_HIT["resets_at"] == 1790000000


def test_auslastung_aus_dem_stream_wird_gemerkt(monkeypatch):
    for k in ("t", "five_hour", "seven_day"):
        monkeypatch.setitem(STREAM_USAGE, k, STREAM_USAGE[k])
    # So schickt claude 2.1 es nach jeder Antwort, auch mit dem setup-token.
    note_rate_limit({"type": "rate_limit_event", "rate_limit_info": {
        "status": "allowed", "resetsAt": 1791743400, "rateLimitType": "five_hour",
        "unifiedWindows": {"five_hour": {"utilization": 0.05, "resetsAt": 1791743400},
                           "seven_day": {"utilization": 0.57, "resetsAt": 1791896400}}}})
    assert round(STREAM_USAGE["five_hour"]["percent"]) == 5
    assert STREAM_USAGE["five_hour"]["resets_at"] == 1791743400
    assert round(STREAM_USAGE["seven_day"]["percent"]) == 57
    assert STREAM_USAGE["t"] > 0


def test_anmeldefehler_wird_erklaert():
    assert friendly_claude_error("Invalid API key · Please run /login").startswith("🔑")


def test_tts_einstellungen_je_sprache_und_alte_werte():
    cur = json.loads(json.dumps(config.DEFAULT_SETTINGS["tts"]))
    # frühe Fassung: eine einzelne Stimme als Text
    config._clean_tts({"voice": "en-us-podcaster-6", "style": "locker"}, cur)
    assert cur["voice"]["en"] == "en-us-podcaster-6"
    assert cur["style"]["de"] == "locker"
    config._clean_tts({"voice": {"de": "../boese<x>", "fr": "x"}, "model": "gibtsnicht"}, cur)
    assert cur["voice"]["de"] == "..boesex"
    assert "fr" not in cur["voice"]
    assert cur["model"] == config.DEFAULT_SETTINGS["tts"]["model"]


def test_alte_plasma_einstellungen_werden_umgestellt(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    f.write_text('{"theme": "plasma", "plasma": true, "background": {"mode": "plasma"}}')
    monkeypatch.setattr(config, "SETTINGS_FILE", f)
    cur = config.load_settings()
    assert cur["theme"] == "space"
    assert cur["background"]["mode"] == "matrix"
    assert "plasma" not in cur


def test_schriftwahl(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    assert config.apply_patch({"font": "jetbrains-mono"})["font"] == "jetbrains-mono"
    assert config.apply_patch({"font": "comic-sans"})["font"] == "jetbrains-mono"
    assert config.apply_patch({"font": ""})["font"] == ""


def test_vertippter_abschnitt_legt_die_einstellungen_nicht_lahm(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    f.write_text('{"team": true, "tickets": "ja", "sound": [1], "lang": "de"}')
    monkeypatch.setattr(config, "SETTINGS_FILE", f)
    cur = config.load_settings()
    assert cur["team"] == config.DEFAULT_SETTINGS["team"] and cur["lang"] == "de"
    assert config.apply_patch({"team": True})["team"]["aktiv"] is False


def test_einstellungen_ohne_objekt_sind_ein_400(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    assert client.post("/api/settings", json=[]).status_code == 400
    assert client.post("/api/settings", content=b"kaputt").status_code == 400


# ---------- Hermes aktuell halten (server/updates.py) ----------

def _hermes_update(monkeypatch, check_ausgabe, check_code=0):
    from server import hermes as hermesmod
    from server import updates
    aufrufe = []

    def run(cmd, timeout=60, env=None):
        aufrufe.append(cmd[1:])
        return (check_code, check_ausgabe) if "--check" in cmd else (0, "✓ Updated")

    fassungen = iter(["Hermes Agent v0.21.6 · local dce1e9b", "Hermes Agent v0.22.2 · local d923a5e"])
    monkeypatch.setattr(updates, "_run", run)
    monkeypatch.setattr(updates, "hermes_version", lambda: next(fassungen))
    monkeypatch.setattr(hermesmod, "hermes_bin", lambda: "/usr/bin/hermes")
    monkeypatch.setattr(hermesmod, "child_env", lambda: {})
    updates._STATE["steps"] = updates._blank_steps()
    updates._update_hermes()
    return aufrufe, updates._STATE["steps"]["hermes"]


def test_hermes_release_kanal_wird_als_neuerung_erkannt(monkeypatch):
    # Wortgleich aus `hermes update --check` am 15.10.2026 (Kanal stable)
    aufrufe, step = _hermes_update(monkeypatch, "→ Update channel: stable\n"
                                   "→ Selected release available: stable v0.22.2 (d923a5eb487a)\n"
                                   "  Run `hermes update` to install it.")
    assert ["update", "--yes"] in aufrufe
    assert step["state"] == "new"


def test_hermes_ohne_neuerung_zieht_nichts(monkeypatch):
    aufrufe, step = _hermes_update(monkeypatch, "→ Update channel: stable\n"
                                   "✓ Up to date with the latest release (stable v0.22.2).")
    assert aufrufe == [["update", "--check"]]
    assert step["state"] == "ok"


def test_gescheiterte_pruefung_sperrt_die_naechste_nicht(tmp_path, monkeypatch):
    # Beim Hochfahren fehlte das Netz noch (DNS): mit Stempel wäre die nächste
    # Prüfung erst sechs Stunden später gekommen.
    import time
    from server import updates
    monkeypatch.setattr(updates, "STAMP_FILE", tmp_path / ".update-stamp")
    monkeypatch.setattr(updates, "WERKZEUGE", ("hermes",))

    def scheitert():
        updates._step("hermes", state="error", msg="Temporary failure in name resolution")

    monkeypatch.setattr(updates, "_update_hermes", scheitert)
    monkeypatch.setattr(updates, "_update_claude", scheitert)
    updates.start("start")
    for _ in range(100):
        if updates._STATE["done"]:
            break
        time.sleep(0.02)
    assert not (tmp_path / ".update-stamp").exists()


def _konto(monkeypatch, creds, tmp_path, token="sk-ant-oat01-alt"):
    monkeypatch.setattr(core, "read_creds", lambda: (creds, "keychain"))
    f = tmp_path / ".oauth-token"
    f.write_text(token + "\n", encoding="utf-8")
    monkeypatch.setattr(core, "TOKEN_FILE", f)


def test_konto_login_gilt_mit_refresh_token_auch_abgelaufen():
    alt = int((time.time() - 3600) * 1000)
    assert core.konto_login({"accessToken": "a", "refreshToken": "r", "expiresAt": alt})
    assert not core.konto_login({"accessToken": "a", "expiresAt": alt})
    assert core.konto_login({"accessToken": "a", "expiresAt": int((time.time() + 3600) * 1000)})
    assert not core.konto_login({})


def test_claude_env_ohne_token_solange_die_kontoanmeldung_gilt(tmp_path, monkeypatch):
    # Mit CLAUDE_CODE_OAUTH_TOKEN lässt `claude --chrome` die Chrome-Werkzeuge
    # stumm weg — auch einen geerbten darf claude dann nicht sehen.
    _konto(monkeypatch, {"accessToken": "a", "refreshToken": "r"}, tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-geerbt")
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in core.claude_env()


def test_claude_env_nimmt_den_alten_token_wenn_kein_konto_da_ist(tmp_path, monkeypatch):
    _konto(monkeypatch, {}, tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert core.claude_env()["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-alt"
