"""Läufe: was passiert, wenn claude im Nachlauf endet (Hintergrundaufgaben offen)."""
import asyncio
import json
import sys

from server import runs


STUB = r'''
import json, sys
sys.stdin.readline()
def out(ev):
    sys.stdout.write(json.dumps(ev) + "\n"); sys.stdout.flush()
out({"type": "system", "subtype": "init", "session_id": "sid-1"})
out({"type": "system", "subtype": "background_tasks_changed",
     "tasks": [{"task_id": "t1", "description": "lange Aufnahme"}]})
out({"type": "stream_event", "event": {"type": "content_block_delta",
     "delta": {"type": "text_delta", "text": "Läuft im Hintergrund."}}})
out({"type": "result", "subtype": "success", "session_id": "sid-1", "usage": {}})
# Prozess geht, obwohl die Hintergrundaufgabe nie fertig gemeldet wurde
'''


def _lauf_der_im_nachlauf_endet(tmp_path, monkeypatch):
    stub = tmp_path / "claude_stub.py"
    stub.write_text(STUB)
    monkeypatch.setattr(runs, "claude_bin", lambda: sys.executable)
    monkeypatch.setattr(runs, "load_persona", lambda: "")
    monkeypatch.setattr(runs, "maybe_notify", lambda run: None)

    async def los():
        run = runs.Run("test-nachlauf", str(tmp_path), None, "", initial_prompt="hallo")
        runs.RUNS[run.id] = run
        await runs.run_claude(run, [sys.executable, str(stub)])
        return run

    return asyncio.run(los())


def test_lauf_der_im_nachlauf_endet_raeumt_den_nachlauf_ab(tmp_path, monkeypatch):
    run = _lauf_der_im_nachlauf_endet(tmp_path, monkeypatch)
    typen = [e["type"] for e in run.events]
    assert "nachlauf" in typen
    # Sonst bleibt die Oberfläche für immer im Nachlauf stehen.
    assert typen[-1] == "nachlauf_ende", typen
    assert run.done


def test_stream_meldet_das_ende_ausdruecklich(tmp_path, monkeypatch, client):
    run = _lauf_der_im_nachlauf_endet(tmp_path, monkeypatch)
    r = client.get(f"/api/stream/{run.id}")
    evs = [json.loads(z[6:]) for z in r.text.splitlines() if z.startswith("data: ")]
    # Ohne "closed" hielt das Frontend den Lauf für abgerissen, dockte jede
    # Sekunde neu an und baute den Verlauf leer neu auf (Flackern ohne Ende).
    assert evs[-1] == {"type": "closed"}
