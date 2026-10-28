"""Bausteine im Chat (server/genui.py)."""
import json
import re
from pathlib import Path

import pytest

from server import config as cfg
from server import genui


def test_beispiele_sind_gueltiges_json(monkeypatch):
    # Die Beispiele sind das, was die Modelle nachmachen — ein Tippfehler
    # darin landete in jeder Antwort als kaputter Codeblock.
    for sprache in ("de", "en"):
        monkeypatch.setattr(cfg, "lang", lambda s=sprache: s)
        bloecke = re.findall(r"```ui\n(.*?)\n```", genui.regeln(), re.S)
        assert len(bloecke) == 2
        typen = {json.loads(b)["type"] for b in bloecke}
        assert typen == {"choices", "event"}


@pytest.mark.parametrize("chat", [True, False])
def test_anleitung_nur_im_chat(tmp_path, monkeypatch, chat):
    # Telegram, Firma und geplante Aufgaben zeigen Markdown roh: dort stünde
    # das JSON eines Bausteins nackt im Text.
    import asyncio

    from server import runs
    (tmp_path / "settings.json").write_text(json.dumps({"lang": "de"}))
    gesehen = []

    async def nichts(run, cmd):
        gesehen.append(cmd)
    monkeypatch.setattr(runs, "run_claude", nichts)
    monkeypatch.setattr(runs, "load_persona", lambda: "Persona")

    async def los():
        runs.start_run("hallo", str(tmp_path), "default", chat=chat)
        await asyncio.sleep(0)
    asyncio.run(los())
    datei = Path(gesehen[0][gesehen[0].index("--append-system-prompt-file") + 1])
    persona = datei.read_text(encoding="utf-8")
    datei.unlink()
    assert ("## Bausteine im Chat" in persona) is chat
