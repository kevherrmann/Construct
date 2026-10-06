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
