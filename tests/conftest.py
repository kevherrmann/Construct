"""Gemeinsame Einrichtung: Projektordner auf den Importpfad, App ohne Start-Hooks.

TestClient ohne `with` löst startup/shutdown NICHT aus — kein Telegram-Bot,
kein Scheduler, keine Update-Prüfung während der Tests.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    import app as appmod
    return TestClient(appmod.app)
