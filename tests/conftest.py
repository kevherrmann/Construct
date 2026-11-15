"""Gemeinsame Einrichtung: Projektordner auf den Importpfad, App ohne Start-Hooks.

TestClient ohne `with` löst startup/shutdown NICHT aus — kein Telegram-Bot,
kein Scheduler, keine Update-Prüfung während der Tests.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _laeufe_im_tmp(tmp_path, monkeypatch):
    """Laufende Läufe merkt sich der Server in laeufe.json — in Tests nicht im Projektordner."""
    from server import runs
    monkeypatch.setattr(runs, "LAEUFE", tmp_path / "laeufe.json")


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    import app as appmod
    # Ohne MATRIX_PASS antwortet der Server nur unter lokalen Namen (DNS-Rebinding).
    return TestClient(appmod.app, base_url="http://127.0.0.1")


def befehl_aus_skript(ordner: Path, skript: Path, name: str = "claude") -> Path:
    """Ein Python-Skript als aufrufbaren Befehl ablegen, wie ein installiertes CLI.

    Unter Linux/macOS ein Shell-Skript mit Ausführrecht. Windows startet so etwas
    nicht (WinError 193): dort eine .cmd, so wie npm das echte claude auch ablegt
    (claude_bin() findet beide über shutil.which bzw. den vollen Pfad).
    """
    import os
    if os.name == "nt":
        exe = ordner / f"{name}.cmd"
        exe.write_text(f'@"{sys.executable}" "{skript}" %*\r\n', encoding="utf-8")
    else:
        exe = ordner / name
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{skript}" "$@"\n')
        exe.chmod(0o755)
    return exe


def nur_fuer_mich_lesbar(p: Path) -> bool:
    """Kommt außer dem eigenen Konto niemand an die Datei? (siehe server/geheim.py)"""
    import os
    if os.name != "nt":
        return p.stat().st_mode & 0o077 == 0
    import subprocess
    aus = subprocess.run(["icacls", str(p)], capture_output=True, text=True, errors="replace").stdout
    # Je Zugriffseintrag eine Zeile mit "Konto:(Rechte)"; die Schlusszeile hat keinen.
    eintraege = [z for z in aus.splitlines() if ":(" in z]
    return len(eintraege) == 1 and os.environ["USERNAME"].lower() in eintraege[0].lower()
