"""Automatische Modellwahl — vorerst nur im Schattenbetrieb.

Bei jeder NEUEN Claude-Session fragt ein kleines Modell (Haiku), welches
Modell zur ersten Nachricht passen würde. Es wird nichts umgeschaltet: der
Vorschlag landet mit dem tatsächlich gewählten Modell in auto_schatten.jsonl.
Nach ein, zwei Wochen zeigt scripts/auto_auswertung.py, wo der Vorschlag
daneben gelegen hätte. Erst danach wird entschieden, ob "Auto" scharf geht.

Nur pro Session, nie mitten drin: der Prompt-Cache gilt je Modell, ein
Wechsel im Gespräch würde den nächsten Schritt teurer machen statt billiger.

Eingeschaltet über settings.json → "auto": {"schatten": true}. Ohne Schalter
in der Oberfläche.
"""
import asyncio
import json
import re
import time

from server import config as cfg
from server.core import BASE_DIR, claude_bin, claude_env

LOG = BASE_DIR / "auto_schatten.jsonl"
KLASSIFIZIERER = "claude-haiku-4-5"
OPTIONEN = ("haiku", "sonnet", "opus", "fable")
# Läuft in /tmp: Sitzungen dort blendet die Sessionliste aus (sessions.py).
ARBEITSORDNER = "/tmp"

FRAGE = """You route requests for a coding assistant (Claude Code with full file and terminal access).
Pick the cheapest model that will still do the job WELL. When unsure, pick the stronger one.

- haiku: trivial, a quick fact, a one-line change, a short lookup.
- sonnet: everyday coding and questions: a normal feature, a bug with a clear cause, writing a text.
- opus: hard or long work: unclear bugs, refactors over many files, architecture, anything that runs for a long time.
- fable: only the very hardest reasoning where opus is likely not enough.

Project folder: {projekt}
First message of the session:
<message>
{text}
</message>

Answer with JSON only, no prose: {{"modell": "haiku|sonnet|opus|fable", "sicherheit": 0.0-1.0, "grund": "max. 12 Wörter, Deutsch"}}"""


def aktiv() -> bool:
    return bool(cfg.load_settings()["auto"]["schatten"])


def _auswerten(raw: str) -> dict:
    """Antwort des Klassifizierers → {modell, sicherheit, grund} (oder Fehler)."""
    try:
        res = json.loads(raw).get("result") or ""
    except Exception:
        res = raw
    m = re.search(r"\{.*\}", res, re.S)
    if not m:
        return {"fehler": f"keine JSON-Antwort: {res[:120]!r}"}
    try:
        d = json.loads(m.group(0))
    except Exception:
        return {"fehler": f"kaputtes JSON: {m.group(0)[:120]!r}"}
    modell = str(d.get("modell", "")).lower().strip()
    if modell not in OPTIONEN:
        return {"fehler": f"unbekanntes Modell {modell!r}"}
    try:
        sicher = max(0.0, min(1.0, float(d.get("sicherheit"))))
    except Exception:
        sicher = None
    return {"modell": modell, "sicherheit": sicher, "grund": str(d.get("grund", ""))[:160]}


async def _frage(text: str, projekt: str) -> dict:
    cmd = [claude_bin() or "claude", "-p", "--model", KLASSIFIZIERER,
           "--output-format", "json", "--tools", "", "--no-session-persistence",
           FRAGE.format(text=text[:4000], projekt=projekt)]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=ARBEITSORDNER, env=claude_env(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=90)
    except asyncio.TimeoutError:
        proc.kill()
        return {"fehler": "Zeitüberschreitung"}
    if proc.returncode:
        return {"fehler": f"exit {proc.returncode}: {err.decode('utf-8', 'replace')[:200]}"}
    return _auswerten(out.decode("utf-8", "replace"))


async def beobachte(run, text: str, gewaehlt: str):
    """Vorschlag holen und protokollieren. Darf den Lauf nie stören."""
    t0 = time.time()
    try:
        vorschlag = await _frage(text, run.cwd)
    except Exception as e:  # noqa: BLE001 - Schattenbetrieb: nie nach außen werfen
        vorschlag = {"fehler": f"{type(e).__name__}: {e}"}
    # Die Session-ID kommt erst mit dem init-Ereignis; kurz darauf warten.
    for _ in range(30):
        if run.session_id or run.done:
            break
        await asyncio.sleep(1)
    eintrag = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_id": run.session_id,
        "run_id": run.id,
        "cwd": run.cwd,
        "nachricht": text[:500],
        "gewaehlt": gewaehlt or "standard",
        "vorschlag": vorschlag.get("modell"),
        "sicherheit": vorschlag.get("sicherheit"),
        "grund": vorschlag.get("grund", ""),
        "fehler": vorschlag.get("fehler", ""),
        "dauer_ms": int((time.time() - t0) * 1000),
    }
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    except OSError:
        pass


def starte(run, text: str, gewaehlt: str):
    """Aus der Chat-Route: nur neue Claude-Sessions, nur wenn eingeschaltet."""
    if not text.strip() or not aktiv():
        return
    asyncio.get_running_loop().create_task(beobachte(run, text, gewaehlt))
