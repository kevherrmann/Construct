"""Datenpfade: die Module liegen in server/, ihre Daten im Projektordner.

Nach dem Verschieben nach server/ würde ein vergessenes Path(__file__).parent
still im falschen Ordner suchen — die App sähe leer aus (keine Einstellungen,
keine Mail-Konten, keine Termine). Dieser Test fängt das.
"""
import importlib
import subprocess
import sys

import pytest

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
MODULES = ["attach", "config", "hermes", "llm", "mail", "telegram_bot", "updates", "core"]


@pytest.mark.parametrize("name", MODULES)
def test_datenordner_ist_der_projektordner(name):
    mod = importlib.import_module(f"server.{name}")
    assert mod.BASE_DIR == ROOT


def test_einstellungen_und_termine_liegen_im_projektordner():
    from server import config
    import cal

    assert config.SETTINGS_FILE.parent == ROOT
    assert cal.EVENTS_FILE.parent == ROOT


def test_cal_laeuft_als_werkzeug_aus_fremdem_ordner(tmp_path):
    # So ruft Cody es auf: python3 "<projekt>/cal.py" … — aus beliebigem Ordner.
    r = subprocess.run([sys.executable, str(ROOT / "cal.py")], cwd=tmp_path,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
