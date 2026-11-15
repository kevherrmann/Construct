"""Läuft ein Prozess noch? Für Linux, macOS und Windows.

Unter Windows taugt os.kill(pid, 0) nicht zum Nachsehen: dort beendet es den
Prozess (bzw. schickt CTRL_C_EVENT). Darum hier über die Prozess-API.
"""
import os
import subprocess
from pathlib import Path


def kennung(pid) -> str:
    """Woran sich ein Prozess über seine PID hinaus wiedererkennen lässt: seine
    Startzeit. PIDs werden wiederverwendet, und laeufe.json übersteht auch einen
    Neustart des Rechners — ohne diesen Abgleich beendete die Rettung irgendein
    Programm, das zufällig dieselbe PID bekam. "" = läuft nicht oder nicht
    feststellbar; dann gilt der Prozess als fremd und wird nie angefasst."""
    if not isinstance(pid, int) or pid <= 0:
        return ""
    try:
        if os.name == "nt":
            # os.kill(pid, 0) wäre hier CTRL_C_EVENT, kein Nachsehen.
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return ""
            try:
                code = ctypes.c_ulong()
                if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
                    return ""
                t = [ctypes.c_ulonglong() for _ in range(4)]   # Erzeugung, Ende, Kernel, User
                if not k.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
                    return ""
                return str(t[0].value)
            finally:
                k.CloseHandle(h)
        if Path("/proc/self/stat").exists():
            # Der Programmname in Klammern darf Leerzeichen enthalten: erst hinter
            # der letzten ")" zählen. Danach Feld 3 (Zustand) … Feld 22 (Startzeit).
            felder = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            if felder[0] in ("Z", "X"):                  # beendet, noch nicht abgeholt
                return ""
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            return f"{boot}:{felder[19]}"
        # macOS und andere ohne /proc
        # LC_ALL=C: sonst hinge der Vergleich an der Sprache, mit der der Server startete
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                           timeout=5, env={**os.environ, "LC_ALL": "C"})
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, IndexError, ValueError, subprocess.SubprocessError):
        return ""


def lebt(pid) -> bool:
    """Gibt es einen laufenden Prozess mit dieser PID?"""
    return bool(kennung(pid))
