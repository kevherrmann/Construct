"""Rechner wach halten, solange ein Lauf arbeitet.

Ohne das schaltet die Energieverwaltung mitten in einer langen Aufgabe den
Monitor ab und schickt den Rechner irgendwann in den Standby, weil an Maus
und Tastatur niemand war. claude stirbt dann zwar nicht, steht aber still,
bis jemand den Rechner weckt.

Gehalten wird mit einem Hilfsprozess, der eine Sperre bei der Arbeitsfläche
anmeldet und sie mit seinem Ende wieder freigibt. Stirbt der Server, stirbt
auch die Sperre (sie hängt am Prozess, nicht an einer Einstellung).
- KDE: kde-inhibit, blockiert Bildschirm aus, Sperre und Standby
- sonst Linux: systemd-inhibit, blockiert wenigstens den Standby
- macOS: caffeinate (Bildschirm und Ruhezustand)

Aus mit CODY_WACH_HALTEN=0.
"""
import asyncio
import os
import shutil
import signal
import sys
import tempfile
from pathlib import Path

from server import config as cfg
from server.runs import RUNS

PRUEF_TAKT = 10    # Sekunden zwischen zwei Blicken auf die Läufe

_proc = None       # laufende Sperre oder None
_kaputt = False    # Sperre ließ sich nicht halten (Container, kein Desktop)


def befehl() -> list[str] | None:
    """Der Hilfsprozess für diese Umgebung, None = geht hier nicht."""
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        return ["caffeinate", "-d", "-i"]
    if not sys.platform.startswith("linux"):
        return None
    if shutil.which("kde-inhibit") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        # kde-inhibit nennt den Befehl als Grund im Akku-Symbol der Leiste. Mit
        # "sleep" stand da "Skript wird ausgeführt: sleep" — darum ein Skript
        # mit sprechendem Namen, das nur wartet.
        ordner = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()) / "construct-wach"
        ordner.mkdir(exist_ok=True)
        name = f"{cfg.assistant_name()} arbeitet"
        (ordner / name).write_text("#!/bin/sh\nexec sleep infinity\n")
        (ordner / name).chmod(0o755)
        return ["env", f"PATH={ordner}:{os.environ.get('PATH', '')}",
                "kde-inhibit", "--power", "--screenSaver", name]
    if shutil.which("systemd-inhibit"):
        return ["systemd-inhibit", "--what=idle:sleep", "--who=CONSTRUCT",
                f"--why={cfg.assistant_name()} arbeitet", "--mode=block", "sleep", "infinity"]
    return None


def arbeitet() -> bool:
    """Läuft gerade irgendein Lauf (Chat, Firma, geplante Aufgabe, Nachlauf)?"""
    return any(not r.done for r in list(RUNS.values()))


async def _an():
    global _proc, _kaputt
    try:
        cmd = befehl()
    except OSError as e:
        print(f"[wach] Hilfsskript: {e}", flush=True)
        cmd = None
    if not cmd:
        _kaputt = True
        return
    try:
        _proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.DEVNULL, start_new_session=True,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    except OSError as e:
        print(f"[wach] {cmd[0]} startet nicht: {e}", flush=True)
        _kaputt = True
        return
    # Ohne Sitzungsbus oder logind beendet sich der Helfer sofort wieder.
    # Dann nicht alle zehn Sekunden neu probieren.
    try:
        await asyncio.wait_for(_proc.wait(), 2)
    except asyncio.TimeoutError:
        print(f"[wach] Rechner bleibt wach ({cmd[0]})", flush=True)
        return
    print(f"[wach] {cmd[0]} endete sofort (Code {_proc.returncode}), wach halten aus", flush=True)
    _proc = None
    _kaputt = True


def aus():
    global _proc
    if _proc and _proc.returncode is None:
        # Die ganze Gruppe: ein beendetes kde-inhibit ließe sein sleep sonst
        # als Waise zurück.
        try:
            os.killpg(_proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        print("[wach] Sperre freigegeben", flush=True)
    _proc = None


async def wach_loop():
    if os.environ.get("CODY_WACH_HALTEN", "1") == "0":
        return
    while not _kaputt:
        try:
            if _proc and _proc.returncode is not None:
                aus()   # von außen beendet: beim nächsten Bedarf neu anmelden
            if arbeitet():
                if not _proc:
                    await _an()
            elif _proc:
                aus()
        except Exception as e:
            print(f"[wach] {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(PRUEF_TAKT)
