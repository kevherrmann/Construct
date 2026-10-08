"""Läufe: was passiert, wenn claude im Nachlauf endet (Hintergrundaufgaben offen)."""
import asyncio
import json
import sys
import time

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


# ---------- Läufe über einen Server-Neustart retten ----------

def _zeile(typ, content, ts, **mehr):
    msg = {"role": typ, "content": content}
    msg.update(mehr.pop("msg", {}))
    return json.dumps({"type": typ, "timestamp": ts, "message": msg, **mehr}) + "\n"


START = 1791273600.0                      # Laufbeginn: 2026-10-06T08:00:00Z
VORHER = "2026-10-06T07:00:00.000Z"      # alter Verlauf einer fortgesetzten Sitzung


def _ts(s):
    """Zeitstempel s Sekunden nach Laufbeginn, wie claude ihn schreibt."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(START + s, timezone.utc).isoformat().replace("+00:00", "Z")


def _sitzung(tmp_path, monkeypatch, zeilen, sid="sid-neu"):
    projekte = tmp_path / "projects"
    (projekte / "-home-x").mkdir(parents=True)
    datei = projekte / "-home-x" / f"{sid}.jsonl"
    datei.write_text("".join(zeilen), encoding="utf-8")
    monkeypatch.setattr(runs, "PROJECTS_DIR", projekte)
    monkeypatch.setattr(runs, "NACHLESEN_TAKT", 0.05)
    monkeypatch.setattr(runs, "maybe_notify", lambda run: None)
    return datei


def _eintrag(pid, sid="sid-neu"):
    return {"pid": pid, "kennung": runs._kennung(pid), "cwd": "/home/x", "start": START,
            "model": "", "session_id": sid}


ANTWORT = [
    _zeile("user", "frühere Frage", VORHER),
    _zeile("assistant", [{"type": "text", "text": "frühere Antwort"}], VORHER,
           msg={"stop_reason": "end_turn"}),
    _zeile("user", "Mach mal den Raum fertig", _ts(1)),
    _zeile("assistant", [{"type": "thinking", "thinking": "hm"}], _ts(2)),
    _zeile("assistant", [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}],
           _ts(3), msg={"stop_reason": "tool_use"}),
    _zeile("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "a.txt"}], _ts(4)),
]
SCHLUSS = [_zeile("assistant", [{"type": "text", "text": "Fertig."}], _ts(5),
                  msg={"stop_reason": "end_turn"})]


def _aufnehmen_und_warten(eintrag, waehrenddessen=None):
    async def los():
        runs.RUNS.pop("lauf-alt", None)
        runs._laeufe_schreiben({"lauf-alt": eintrag})
        runs.aufnehmen()
        run = runs.RUNS["lauf-alt"]
        if waehrenddessen:
            await waehrenddessen(run)
        await run.task
        return run
    return asyncio.run(los())


def test_nach_neustart_steht_die_fertige_antwort_unter_derselben_lauf_id(tmp_path, monkeypatch):
    _sitzung(tmp_path, monkeypatch, ANTWORT + SCHLUSS)
    run = _aufnehmen_und_warten(_eintrag(None))
    assert [e["type"] for e in run.events] == [
        "session", "thinking_marker", "tool", "tool_result", "text", "done"]
    # Der alte Verlauf der fortgesetzten Sitzung gehört nicht zu diesem Lauf
    assert run.events[4]["text"] == "Fertig."
    assert run.done and not runs.LAEUFE.exists()


def test_aufgenommener_lauf_liest_mit_solange_claude_noch_schreibt(tmp_path, monkeypatch):
    datei = _sitzung(tmp_path, monkeypatch, ANTWORT)
    import subprocess
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])

    async def weiter(run):
        await asyncio.sleep(0.3)
        assert not run.done                    # Prozess lebt: Lauf gilt als laufend
        assert run.events[-1]["type"] == "tool_result"
        with datei.open("a", encoding="utf-8") as f:
            f.write(SCHLUSS[0])
        await asyncio.sleep(0.3)
        proc.kill()
        proc.wait()

    try:
        run = _aufnehmen_und_warten(_eintrag(proc.pid), weiter)
    finally:
        proc.kill()
    assert [e["type"] for e in run.events][-2:] == ["text", "done"]


def test_abgerissene_antwort_sagt_es_statt_still_zu_enden(tmp_path, monkeypatch):
    _sitzung(tmp_path, monkeypatch, ANTWORT)       # endet mitten im Werkzeug-Aufruf
    run = _aufnehmen_und_warten(_eintrag(None))
    assert run.events[-1]["type"] == "error"
    assert "neu gestartet" in run.events[-1]["message"] or "restarted" in run.events[-1]["message"]


def test_lauf_ohne_sitzung_wird_nicht_aufgenommen(tmp_path, monkeypatch):
    _sitzung(tmp_path, monkeypatch, [])
    runs.RUNS.pop("lauf-alt", None)
    runs._laeufe_schreiben({"lauf-alt": _eintrag(None, sid=None)})
    runs.aufnehmen()
    assert "lauf-alt" not in runs.RUNS and not runs.LAEUFE.exists()


def test_fremder_prozess_mit_derselben_pid_zaehlt_nicht():
    import subprocess
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        kennung = runs._kennung(proc.pid)
        assert kennung and runs._lebt(proc.pid, kennung)
        # Dieselbe PID, aber ein anderer Prozess (anderer Start): nicht unserer
        assert not runs._lebt(proc.pid, kennung + "x")
        assert not runs._lebt(proc.pid, "")          # alter Eintrag ohne Kennung
    finally:
        proc.kill()
        proc.wait()
    assert not runs._lebt(proc.pid, kennung)


def test_fremder_prozess_auf_der_pid_eines_firmen_zugs_wird_nicht_beendet(tmp_path, monkeypatch):
    # laeufe.json übersteht einen Neustart des Rechners; die PID gehört dann
    # womöglich einem ganz anderen Programm (Janus' Audit, 06.10.2026).
    import subprocess
    _sitzung(tmp_path, monkeypatch, ANTWORT)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        runs.RUNS.pop("lauf-alt", None)
        eintrag = {**_eintrag(proc.pid), "auftrag": "a-1", "kennung": "anderer-start"}
        runs._laeufe_schreiben({"lauf-alt": eintrag})
        runs.aufnehmen()
        assert not runs.LAEUFE.exists()
        time.sleep(0.3)
        assert proc.poll() is None                  # lebt noch
    finally:
        proc.kill()
        proc.wait()


def test_laufender_lauf_steht_in_laeufe_json_und_verschwindet_am_ende(tmp_path, monkeypatch):
    staende = []
    echt = runs._laeufe_schreiben
    monkeypatch.setattr(runs, "_laeufe_schreiben", lambda d: (staende.append(json.loads(json.dumps(d))), echt(d)))
    run = _lauf_der_im_nachlauf_endet(tmp_path, monkeypatch)
    eintraege = [d[run.id] for d in staende if run.id in d]
    assert eintraege and eintraege[-1]["session_id"] == "sid-1"
    assert eintraege[0]["pid"] > 0
    assert staende[-1] == {} and not runs.LAEUFE.exists()


def test_zug_der_firma_wird_nach_neustart_beendet_statt_aufgenommen(tmp_path, monkeypatch):
    # Sein Bus-Token ist mit dem alten Server weg, und der Dispatcher stellt die
    # Nachricht neu zu: liefe er weiter, schrieben zwei Prozesse in eine Sitzung.
    import subprocess
    _sitzung(tmp_path, monkeypatch, ANTWORT)
    proc = subprocess.Popen([sys.executable, "-c", "import time; print(1, flush=True); time.sleep(30)"],
                            stdout=subprocess.PIPE)
    proc.stdout.readline()
    try:
        runs.RUNS.pop("lauf-alt", None)
        runs._laeufe_schreiben({"lauf-alt": {**_eintrag(proc.pid), "auftrag": "a-1"}})
        runs.aufnehmen()
        assert "lauf-alt" not in runs.RUNS and not runs.LAEUFE.exists()
        assert proc.wait(timeout=5) is not None
    finally:
        proc.kill()
        proc.wait()


def test_telegram_meldung_ohne_markerzeile(monkeypatch):
    gesendet = []
    monkeypatch.setattr(runs.tgmod, "load_conf",
                        lambda: {"enabled": True, "token": "x", "chat_id": "1", "notify": True})
    monkeypatch.setattr(runs.tgmod, "send_owner", gesendet.append)
    run = runs.Run("test-notify", "/tmp", None, "")
    run.started -= 3600
    run.last_text = "Fertig gebaut.\n\n[[firma: Kachel bauen]]"
    runs.maybe_notify(run)
    import time
    for _ in range(50):
        if gesendet:
            break
        time.sleep(0.02)
    assert gesendet and "Fertig gebaut." in gesendet[0] and "[[firma" not in gesendet[0]


def test_markerzeile_eines_aufgenommenen_laufs_wirkt(tmp_path, monkeypatch):
    # Nach dem Neustart kam die Antwort zwar an, ihr Marker verpuffte aber.
    sid = "abcd1234-0000-0000-0000-00000000rest"
    gesehen = []
    monkeypatch.setattr(runs, "_firma_marke", lambda run: gesehen.append(run.last_text))
    _sitzung(tmp_path, monkeypatch, [
        _zeile("user", "Mach die Uhr", _ts(1), uuid="u-1"),
        _zeile("assistant", [{"type": "text", "text": "Mach ich.\n\n[[firma: Uhr]]"}], _ts(2),
               msg={"stop_reason": "end_turn"}),
    ], sid=sid)
    _aufnehmen_und_warten(_eintrag(None, sid=sid))
    assert gesehen == ["Mach ich.\n\n[[firma: Uhr]]"]


def test_geretteter_lauf_trennt_aufeinanderfolgende_textbloecke():
    run = runs.Run("r-text", "/tmp")
    run.started = 0
    leser = runs._Leser(run)
    leser.prompt_gesehen = True
    ts = "2030-01-01T00:00:00Z"
    for text in ("Ich schau nach.", "Passt."):
        leser.eintrag({"type": "assistant", "timestamp": ts,
                       "message": {"content": [{"type": "text", "text": text}]}})
    assert run.last_text == "Ich schau nach.\n\nPasst."


# ---------- Helfer (Agent/Task) für die Hologramme im Raum ----------
# Ereignisse wie aus einem echten Lauf (claude 2.1.294, 08.10.2026), gekürzt.

AGENT = "toolu_0132jWkGJw8rVyPgopMoXXKu"


def _sys(subtype, **mehr):
    return {"type": "system", "subtype": subtype, "task_id": "aee2cbfad9a6acc9c", **mehr}


def _msg(typ, content, parent=None):
    return {"type": typ, "parent_tool_use_id": parent, "message": {"role": typ, "content": content}}


HELFER_LAUF = [
    {"type": "system", "subtype": "init", "session_id": "sid-h"},
    _msg("assistant", [{"type": "tool_use", "id": AGENT, "name": "Agent", "input": {
        "description": "Datei eins.txt lesen", "subagent_type": "Explore", "prompt": "Lies …"}}]),
    _sys("task_started", tool_use_id=AGENT, description="Datei eins.txt lesen",
         subagent_type="Explore", is_backgrounded=False, task_type="local_agent"),
    _msg("user", [{"type": "text", "text": "Lies …"}], AGENT),
    _sys("task_progress", tool_use_id=AGENT, description="Reading eins.txt",
         subagent_type="Explore", last_tool_name="Read"),
    _msg("assistant", [{"type": "tool_use", "id": "toolu_read", "name": "Read",
                        "input": {"file_path": "/tmp/helfertest/eins.txt"}}], AGENT),
    _msg("user", [{"type": "tool_result", "tool_use_id": "toolu_read", "content": "1\ta"}], AGENT),
    _sys("task_updated", patch={"status": "completed"}),
    _sys("task_notification", tool_use_id=AGENT, status="completed", summary="a"),
    _msg("user", [{"type": "tool_result", "tool_use_id": AGENT, "content": "a"}]),
    _msg("assistant", [{"type": "text", "text": "a"}]),
    {"type": "result", "subtype": "success", "session_id": "sid-h", "usage": {}},
]


def _lauf_mit(tmp_path, monkeypatch, zeilen):
    """run_claude gegen ein falsches claude, das genau diese Zeilen ausgibt."""
    stub = tmp_path / "claude_stub.py"
    stub.write_text("import sys\nsys.stdin.readline()\nsys.stdout.write(sys.argv[1])\n")
    monkeypatch.setattr(runs, "claude_bin", lambda: sys.executable)
    monkeypatch.setattr(runs, "maybe_notify", lambda run: None)
    text = "".join(json.dumps(z, ensure_ascii=False) + "\n" for z in zeilen)

    async def los():
        run = runs.Run("test-helfer", str(tmp_path), None, "", initial_prompt="hallo")
        runs.RUNS[run.id] = run
        await runs.run_claude(run, [sys.executable, str(stub), text])
        return run

    return asyncio.run(los())


def test_helfer_meldet_start_fortschritt_und_ende(tmp_path, monkeypatch):
    run = _lauf_mit(tmp_path, monkeypatch, HELFER_LAUF)
    assert [e for e in run.events if e["type"] == "helfer"] == [
        {"type": "helfer", "id": AGENT, "stand": "start", "beschreibung": "Datei eins.txt lesen",
         "typ": "Explore", "hintergrund": False},
        {"type": "helfer", "id": AGENT, "stand": "laeuft", "detail": "Reading eins.txt",
         "werkzeug": "Read"},
        {"type": "helfer", "id": AGENT, "stand": "fertig"},
    ]
    assert not run.helfer


def test_schritte_des_helfers_tragen_ihren_helfer(tmp_path, monkeypatch):
    run = _lauf_mit(tmp_path, monkeypatch, HELFER_LAUF)
    werkzeuge = [(e["type"], e["id"], e.get("parent")) for e in run.events
                 if e["type"] in ("tool", "tool_result")]
    # Sonst stand im Raum der Assistent selbst am Regal, obwohl der Helfer las.
    assert werkzeuge == [
        ("tool", AGENT, None),
        ("tool", "toolu_read", AGENT),
        ("tool_result", "toolu_read", AGENT),
        ("tool_result", AGENT, None),
    ]
    assert "parent" not in run.events[1]


def test_helfer_mit_fehler_und_bash_im_hintergrund_ist_keiner(tmp_path, monkeypatch):
    zeilen = [
        {"type": "system", "subtype": "init", "session_id": "sid-h"},
        # Bash mit run_in_background meldet sich über dieselben task_*-Ereignisse
        _sys("task_started", tool_use_id="toolu_bash", description="sleep 30",
             is_backgrounded=True, task_type="local_bash"),
        _sys("task_notification", tool_use_id="toolu_bash", status="completed"),
        _sys("task_started", tool_use_id=AGENT, description="X", subagent_type="Explore",
             is_backgrounded=True, task_type="local_agent"),
        _sys("task_notification", tool_use_id=AGENT, status="killed"),
        {"type": "result", "subtype": "success", "session_id": "sid-h", "usage": {}},
    ]
    run = _lauf_mit(tmp_path, monkeypatch, zeilen)
    helfer = [(e["id"], e["stand"]) for e in run.events if e["type"] == "helfer"]
    assert helfer == [(AGENT, "start"), (AGENT, "fehler")]


def test_schritt_eines_helfers_im_nachlauf_ist_kein_neuer_zug(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "NACHLAUF_MAX", 3600)
    zeilen = [
        {"type": "system", "subtype": "init", "session_id": "sid-h"},
        {"type": "system", "subtype": "background_tasks_changed",
         "tasks": [{"task_id": "aee2cbfad9a6acc9c", "description": "Datei lesen"}]},
        _sys("task_started", tool_use_id=AGENT, description="Datei lesen",
             subagent_type="general-purpose", is_backgrounded=True, task_type="local_agent"),
        {"type": "result", "subtype": "success", "session_id": "sid-h", "usage": {}},
        # Nachlauf: der Helfer arbeitet weiter, der Assistent hat noch nichts gesagt
        _msg("assistant", [{"type": "tool_use", "id": "toolu_read", "name": "Read",
                            "input": {"file_path": "/tmp/x"}}], AGENT),
    ]
    run = _lauf_mit(tmp_path, monkeypatch, zeilen)
    typen = [e["type"] for e in run.events]
    assert "nachlauf" in typen and "neuer_zug" not in typen
