"""Werkzeuge, die Claude im Chat aufruft, schreiben in eine Pipe.

Unter Windows ist das ohne Vorkehrung cp1252: cal.py speicherte den Termin und
starb dann an seinem "✓" (UnicodeEncodeError). Claude sah nur den Fehler und
hätte den Termin womöglich ein zweites Mal eingetragen.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ohne_utf8_hilfe() -> dict:
    env = dict(os.environ)
    for k in ("PYTHONUTF8", "PYTHONIOENCODING"):
        env.pop(k, None)
    return env


def test_cal_add_ueberlebt_die_pipe(tmp_path):
    shutil.copy(ROOT / "cal.py", tmp_path / "cal.py")    # events.json liegt neben cal.py
    r = subprocess.run([sys.executable, str(tmp_path / "cal.py"), "add", "2030-01-01", "14:00", "Zahnärztin"],
                       capture_output=True, env=_ohne_utf8_hilfe(), cwd=tmp_path)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "✓" in r.stdout.decode("utf-8") and "Zahnärztin" in r.stdout.decode("utf-8")
    assert [e["title"] for e in json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))] == ["Zahnärztin"]

