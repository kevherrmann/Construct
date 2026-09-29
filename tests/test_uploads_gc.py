"""Anhänge aufräumen (server/uploads_gc.py)."""
import os
import time

import pytest

from server import uploads_gc as gc


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    up, proj, base = tmp_path / "uploads", tmp_path / "projects", tmp_path / "base"
    for d in (up, proj / "p", base):
        d.mkdir(parents=True)
    monkeypatch.setattr(gc, "UPLOAD_DIR", up)
    monkeypatch.setattr(gc, "PROJECTS_DIR", proj)
    monkeypatch.setattr(gc, "BASE_DIR", base)
    return up, proj / "p", base


def mk(up, name, age_days=0):
    f = up / name
    f.write_bytes(b"x")
    t = time.time() - age_days * 86400
    os.utime(f, (t, t))
    return f


def test_geloeschte_session_nimmt_ihre_anhaenge_mit(dirs):
    up, proj, base = dirs
    mk(up, "a.png"), mk(up, "b.pdf"), mk(up, "c.png")
    (up / "b.pdf.txt").write_text("auszug")
    sess = b'[Image uploaded by the user: /alt/matrix-chat/uploads/a.png] /uploads/b.pdf'
    (proj / "andere.jsonl").write_bytes(b"/uploads/c.png")
    assert gc.names_in(sess) == {"a.png", "b.pdf"}
    assert gc.drop_unused({"a.png", "b.pdf", "c.png"}) == ["a.png", "b.pdf"]
    assert sorted(p.name for p in up.iterdir()) == ["c.png"]


def test_hintergrundbild_aus_den_einstellungen_bleibt(dirs):
    up, proj, base = dirs
    mk(up, "bg.jpg", age_days=30)
    (base / "settings.json").write_text('{"bg": {"image": "/uploads/bg.jpg"}}')
    assert gc.sweep() == []
    assert (up / "bg.jpg").exists()


def test_sweep_loescht_nur_alte_verwaiste(dirs):
    up, proj, base = dirs
    mk(up, "alt.png", age_days=10)
    mk(up, "neu.png", age_days=1)
    mk(up, "genutzt.png", age_days=10)
    (proj / "s.jsonl").write_bytes(b"uploads/genutzt.png")
    assert gc.sweep() == ["alt.png"]
    assert sorted(p.name for p in up.iterdir()) == ["genutzt.png", "neu.png"]
