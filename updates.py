"""Werkzeuge aktuell halten — Claude Code und Hermes, beim Start von CONSTRUCT.

Warum überhaupt: beide Maschinen sind eigenständige Programme, die CONSTRUCT
nur benutzt (`claude -p`, `hermes acp`). Deren Auto-Update ist bei nativer
Installation ab Werk AUS, und wer nie ins Terminal geht, bleibt still auf einer
alten Fassung sitzen — inklusive fehlender Befehle, die es längst gibt.

Bewusst KEIN eigener Versionsvergleich über eine Download-Adresse: welcher
Kanal für welche Installationsart gilt (nativ, npm, git), weiß das jeweilige
Werkzeug selbst am besten. Wir rufen also schlicht dessen Update-Befehl auf und
lesen die Fassung davor und danach aus — das ist gleichzeitig Prüfung und
Ausführung, und es kann nicht auf den falschen Kanal zeigen.

Ablauf: ein Hintergrund-Thread, geteilter Zustand, das Frontend fragt nach —
dasselbe Muster wie die Installation in app.py und hermes.py. Der Start von
CONSTRUCT wartet also nie auf das Netz.
"""
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import hermes as hermesmod

BASE_DIR = Path(__file__).parent
# Wann zuletzt gesucht wurde. Eigene Datei statt settings.json: das hier ist
# Laufzeitspur, keine Einstellung — und settings.json schreibt der Nutzer.
STAMP_FILE = BASE_DIR / ".update-stamp"

# Ein Update lädt und entpackt ein paar hundert MB. Großzügig, aber endlich:
# ohne Deckel bliebe ein hängender Download für immer als "läuft…" stehen.
TIMEOUT = 600
MAX_LOG = 120

WERKZEUGE = ("claude", "hermes")

_LOCK = threading.Lock()
_STATE = {
    "running": False,
    "done": True,
    "started": 0.0,
    "finished": 0.0,
    # Warum der Lauf angestoßen wurde — das Frontend zeigt einen Boot-Lauf
    # dezent an, einen angeklickten dagegen mit Protokoll.
    "trigger": "",
    "changed": False,
    "log": [],
    "steps": {},
}


def _blank_steps() -> dict:
    return {w: {"state": "idle", "from": "", "to": "", "msg": ""} for w in WERKZEUGE}


_STATE["steps"] = _blank_steps()


# ---------- Fassungen auslesen ----------
def _run(cmd, timeout=60, env=None):
    """Unterprozess, der nie wirft. Rückgabe: (code, ausgabe)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env=env, stdin=subprocess.DEVNULL)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, f"Zeitüberschreitung nach {timeout}s"
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def claude_bin() -> str:
    return shutil.which("claude") or ""


def claude_version() -> str:
    if not claude_bin():
        return ""
    code, out = _run([claude_bin(), "--version"], timeout=30)
    if code != 0 or not out:
        return ""
    # "2.1.245 (Claude Code)" -> "2.1.245"
    return out.splitlines()[0].split(" ")[0].strip()


def claude_install_method() -> str:
    """nativ / npm — entscheidet, WIE aktualisiert wird.

    Eine per npm global installierte Fassung lässt sich nicht mit `claude
    update` austauschen; umgekehrt würde ein npm-Aufruf neben einer nativen
    Installation eine zweite, konkurrierende ablegen. Die Wahrheit steht in
    ~/.claude.json, geschrieben vom Installer selbst.
    """
    try:
        raw = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
        m = str(raw.get("installMethod") or "").strip().lower()
        if m in ("native", "nativ"):
            return "nativ"
        if m in ("npm", "global"):
            return "npm"
    except Exception:
        pass
    # Kein Eintrag: am Pfad erkennen. Der native Installer legt die Fassungen
    # unter ~/.local/share/claude/versions ab.
    p = claude_bin()
    try:
        real = os.path.realpath(p) if p else ""
    except Exception:
        real = p
    if "node_modules" in real or "/npm" in real:
        return "npm"
    return "nativ" if real else ""


def hermes_version() -> str:
    """Volle Kennung — die zählt beim Vergleich vorher/nachher.

    Sie enthält neben der Nummer auch den Stand des Quelltexts ("upstream
    987064ca"). Bei einer git-Installation ändert sich oft nur der, während die
    Nummer stehen bleibt; wer nur auf die Nummer schaut, meldet dann fälschlich
    "keine Änderung".
    """
    v = hermesmod.version()
    return v.strip() if v else ""


def _kurz(v: str) -> str:
    """Fürs Auge: "Hermes Agent v0.20.5 (2026.8.19) · upstream 98706" -> "v0.20.5"."""
    import re
    m = re.search(r"v?\d+\.\d+\.\d+", v or "")
    return m.group(0) if m else (v or "")[:24]


# ---------- Ein Werkzeug aktualisieren ----------
def _log(line: str):
    line = str(line).rstrip()[:400]
    if line:
        _STATE["log"].append(line)
        del _STATE["log"][:-MAX_LOG]


def _step(w: str, **kw):
    _STATE["steps"][w].update(kw)


def _update_claude():
    if not claude_bin():
        _step("claude", state="skip", msg="nicht installiert")
        return
    before = claude_version()
    method = claude_install_method()
    _step("claude", state="run", **{"from": before})
    _log(f"» Claude Code {before or '?'} ({method or 'unbekannt'}) — suche Update …")

    if method == "npm":
        npm = shutil.which("npm")
        if not npm:
            _step("claude", state="error", msg="npm fehlt")
            _log("!! npm nicht im PATH — Claude Code kann nicht aktualisiert werden.")
            return
        cmd = [npm, "install", "-g", "@anthropic-ai/claude-code@latest"]
    else:
        cmd = [claude_bin(), "update"]

    code, out = _run(cmd, timeout=TIMEOUT)
    for line in out.splitlines()[-12:]:
        _log("   " + line)
    after = claude_version()
    if code != 0 and before == after:
        _step("claude", state="error", to=after, msg=(out.splitlines() or ["Fehler"])[-1][:200])
        _log(f"!! Claude-Update fehlgeschlagen (Code {code}) — es läuft weiter mit {before}.")
        return
    if after and before and after != before:
        _step("claude", state="new", to=after, msg=f"{before} → {after}")
        _STATE["changed"] = True
        _log(f"✓ Claude Code aktualisiert: {before} → {after}")
    else:
        _step("claude", state="ok", to=after or before, msg="aktuell")
        _log(f"✓ Claude Code ist aktuell ({after or before})")


def _update_hermes():
    if not hermesmod.hermes_bin():
        _step("hermes", state="skip", msg="nicht installiert")
        return
    if os.name != "posix":
        _step("hermes", state="skip", msg="nur Linux / macOS")
        return
    before = hermes_version()
    _step("hermes", state="run", **{"from": _kurz(before)})
    _log(f"» Hermes {_kurz(before) or '?'} — suche Update …")
    env = hermesmod.child_env()

    # Erst fragen, dann ziehen: `hermes update` baut auch ohne Neuerung die
    # Abhängigkeiten neu auf und braucht dafür Minuten. --check kostet Sekunden.
    code, out = _run([hermesmod.hermes_bin(), "update", "--check"], timeout=120, env=env)
    for line in out.splitlines()[-4:]:
        _log("   " + line)
    text = out.lower()
    # Gezogen wird nur bei eindeutigem Befund. Herum wäre gefährlicher: eine
    # umformulierte Meldung würde sonst bei JEDEM Start einen kompletten
    # Neubau der Abhängigkeiten auslösen. Bleibt die Erkennung mal stumm,
    # steht die Antwort von --check im Protokoll und fällt auf.
    verfuegbar = any(w in text for w in
                     ("update available", "behind", "outdated", "new version"))
    if code != 0 and not verfuegbar:
        _step("hermes", state="error", to=_kurz(before),
              msg=(out.splitlines() or ["Prüfung fehlgeschlagen"])[-1][:200])
        _log(f"!! Hermes-Prüfung fehlgeschlagen (Code {code}).")
        return
    if not verfuegbar:
        _step("hermes", state="ok", to=_kurz(before), msg="aktuell")
        _log(f"✓ Hermes ist aktuell ({_kurz(before)})")
        return

    # --yes: der Aufruf läuft ohne Terminal, eine Rückfrage würde ihn aufhängen.
    # Das Sicherungspaket bleibt an (Vorgabe von hermes) — hier wird ohne
    # Aufsicht aktualisiert, da ist der Rückweg mehr wert als die Minute.
    code, out = _run([hermesmod.hermes_bin(), "update", "--yes"], timeout=TIMEOUT, env=env)
    for line in out.splitlines()[-15:]:
        _log("   " + line)
    after = hermes_version()
    if code != 0 and before == after:
        _step("hermes", state="error", to=_kurz(after), msg=(out.splitlines() or ["Fehler"])[-1][:200])
        _log(f"!! Hermes-Update fehlgeschlagen (Code {code}) — es läuft weiter mit {_kurz(before)}.")
        return
    if after and before and after != before:
        _step("hermes", state="new", to=_kurz(after), msg=f"{_kurz(before)} → {_kurz(after)}")
        _STATE["changed"] = True
        _log(f"✓ Hermes aktualisiert: {_kurz(before)} → {_kurz(after)}")
    else:
        _step("hermes", state="ok", to=_kurz(after or before), msg="aktuell")
        _log(f"✓ Hermes ist aktuell ({_kurz(after or before)})")


# ---------- Lauf ----------
def state() -> dict:
    st = dict(_STATE)
    st["log"] = list(_STATE["log"])[-MAX_LOG:]
    st["steps"] = json.loads(json.dumps(_STATE["steps"]))
    st["last_check"] = _last_check()
    return st


def _last_check() -> float:
    try:
        return float(json.loads(STAMP_FILE.read_text(encoding="utf-8")).get("ts") or 0)
    except Exception:
        return 0.0


def _stamp():
    try:
        STAMP_FILE.write_text(json.dumps({"ts": time.time()}), encoding="utf-8")
    except Exception:
        pass


def start(trigger: str = "manuell", only=None) -> dict:
    """Lauf anstoßen. Kehrt sofort zurück; der Fortschritt steht in state()."""
    with _LOCK:
        if _STATE["running"]:
            return {"ok": True, "already": True}
        _STATE.update(running=True, done=False, started=time.time(), finished=0.0,
                      trigger=trigger, changed=False, log=[], steps=_blank_steps())

    todo = [w for w in WERKZEUGE if not only or w in only]

    def worker():
        try:
            for w in todo:
                try:
                    (_update_claude if w == "claude" else _update_hermes)()
                except Exception as e:
                    _step(w, state="error", msg=f"{type(e).__name__}: {e}")
                    _log(f"!! {w}: {type(e).__name__}: {e}")
            _stamp()
        finally:
            _STATE.update(running=False, done=True, finished=time.time())

    threading.Thread(target=worker, daemon=True, name="updates").start()
    return {"ok": True}


def boot_check() -> dict:
    """Beim Start: aktualisieren, wenn eingeschaltet und lange genug her.

    Der Abstand verhindert, dass ein Nachmittag mit fünf Neustarts fünf
    Netzrunden auslöst. `interval_h: 0` heißt: bei jedem Start.
    """
    try:
        import config as cfg
        s = cfg.load_settings().get("updates") or {}
    except Exception:
        s = {}
    if not s.get("auto", True):
        return {"ok": True, "skipped": "abgeschaltet"}
    try:
        iv = max(0, int(s.get("interval_h", 6)))
    except Exception:
        iv = 6
    age = time.time() - _last_check()
    if iv and age < iv * 3600:
        return {"ok": True, "skipped": f"zuletzt vor {int(age // 60)} min geprüft"}
    return start(trigger="start")
