"""Dateien mit Geheimnissen (Schlüssel, Kennwörter, Tokens) nur für das eigene Konto.

Unter Linux/macOS heißt das chmod 600. Unter Windows wirkt chmod nur auf den
Schreibschutz: die Datei erbt die Zugriffsliste ihres Ordners, und auf einem
zweiten Laufwerk (D:\\) dürfen dort meist alle angemeldeten Benutzer lesen und
ändern. Darum dort eine eigene Zugriffsliste, die nur das eigene Konto kennt.
"""
import functools
import getpass
import os
import subprocess
from pathlib import Path

_OHNE_FENSTER = 0x08000000      # CREATE_NO_WINDOW: kein aufblitzendes Konsolenfenster


@functools.lru_cache(maxsize=1)
def _konto() -> str:
    """Das eigene Konto für icacls, am liebsten als SID ("*S-1-5-21-…").

    Der Name allein ist unsicher: über SSH meldet USERDOMAIN etwa "WORKGROUP",
    das Konto heißt aber RECHNER\\name. whoami /user liefert die SID in jeder
    Sprache gleich."""
    try:
        r = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True,
                           timeout=15, creationflags=_OHNE_FENSTER)
        sid = r.stdout.strip().split(",")[-1].strip('"')
        if sid.startswith("S-1-"):
            return f"*{sid}"
    except (OSError, subprocess.SubprocessError):
        pass
    return os.environ.get("USERNAME") or getpass.getuser()


def nur_fuer_mich(p: Path) -> None:
    """Nur das eigene Konto darf die Datei lesen und schreiben.

    Unter Linux/macOS wirft ein Fehler wie chmod selbst (OSError). Unter Windows
    ist icacls nur ein Zusatzschutz: scheitert es, bleibt die Datei, wie sie war,
    statt den Vorgang (Schlüssel speichern) abzubrechen."""
    if os.name != "nt":
        Path(p).chmod(0o600)
        return
    try:
        # /inheritance:r wirft die geerbten Einträge raus, /grant:r ersetzt statt zu ergänzen.
        subprocess.run(["icacls", str(p), "/inheritance:r", "/grant:r", f"{_konto()}:F"],
                       capture_output=True, timeout=15, creationflags=_OHNE_FENSTER)
    except (OSError, subprocess.SubprocessError):
        pass
