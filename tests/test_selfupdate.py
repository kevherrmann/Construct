"""Selbst-Update beim Start (selfupdate.py) — mit echten Wegwerf-Repos.

Entwickelt wird auf mehreren Rechnern; lokale Änderungen dürfen das Update
nicht grundlos blockieren, aber auch nie verloren gehen.
"""
import shutil
import subprocess

import pytest

import selfupdate

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="git fehlt")

ID = ["-c", "user.name=t", "-c", "user.email=t@t"]


def sh(cwd, *args):
    subprocess.run(["git", *ID, *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """Rechner A (wird aktualisiert) und B (pusht) an einem gemeinsamen origin."""
    origin, a, b = tmp_path / "origin.git", tmp_path / "a", tmp_path / "b"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(a)], check=True, capture_output=True)
    (a / "runs.py").write_text("x\n")
    (a / "app.py").write_text("1\n")
    sh(a, "checkout", "-q", "-b", "main")
    sh(a, "add", ".")
    sh(a, "commit", "-qm", "1")
    sh(a, "push", "-q", "-u", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(origin), str(b)], check=True, capture_output=True)
    monkeypatch.setattr(selfupdate, "BASE_DIR", a)
    monkeypatch.delenv("CONSTRUCT_NO_UPDATE", raising=False)
    return a, b


def push(b, name, text):
    (b / name).write_text(text)
    sh(b, "add", name)
    sh(b, "commit", "-qm", name)
    sh(b, "push", "-q")


def test_unbeteiligte_lokale_aenderung_bleibt(repos):
    a, b = repos
    push(b, "runs.py", "x\nneu\n")
    (a / "app.py").write_text("lokal\n")
    assert selfupdate.main() == selfupdate.UPDATED
    assert (a / "runs.py").read_text() == "x\nneu\n"
    assert (a / "app.py").read_text() == "lokal\n"


def test_gleiche_aenderung_schon_auf_github(repos):
    a, b = repos
    push(b, "runs.py", "x\n--chrome\n")
    (a / "runs.py").write_text("x\n--chrome\n")
    assert selfupdate.main() == selfupdate.UPDATED
    assert (a / "runs.py").read_text() == "x\n--chrome\n"


def test_neue_datei_liegt_schon_gleich_da(repos):
    a, b = repos
    push(b, "neu.py", "n\n")
    (a / "neu.py").write_text("n\n")
    assert selfupdate.main() == selfupdate.UPDATED


def test_abweichende_aenderung_blockt_und_bleibt(repos):
    a, b = repos
    push(b, "app.py", "2\n")
    push(b, "runs.py", "x\ny\n")
    (a / "runs.py").write_text("x\ny\n")        # gleich — aber ...
    (a / "app.py").write_text("meins\n")        # ... das hier kollidiert
    assert selfupdate.main() == 0
    # nichts angefasst, auch die "gleiche" Datei nicht
    assert (a / "app.py").read_text() == "meins\n"
    assert (a / "runs.py").read_text() == "x\ny\n"


def test_umlaut_datei_stoert_nicht(repos):
    a, b = repos
    push(b, "runs.py", "x\nneu\n")
    (a / "Übersicht.md").write_text("notiz\n")
    assert selfupdate.main() == selfupdate.UPDATED
    assert (a / "Übersicht.md").read_text() == "notiz\n"
