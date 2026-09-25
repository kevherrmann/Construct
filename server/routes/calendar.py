"""API: Kalender-Termine und Tagebuch (woran wann gearbeitet wurde)."""
import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import cal
import hermes as hermesmod
import llm as llmmod

from server.core import PROJECTS_DIR, extract_text
from server.sessions import _fremde_firma, _verborgen, load_meta

router = APIRouter()


# ---------- Kalender ----------
@router.get("/api/events")
def events_list():
    """Alle Termine (die Web-UI rendert daraus den Kalender)."""
    return cal.load_events()


@router.post("/api/events")
async def events_add(req: Request):
    body = await req.json()
    date = (body.get("date") or "").strip()
    title = (body.get("title") or "").strip()
    if not date or not title:
        return JSONResponse({"error": "date und title sind nötig"}, status_code=400)
    repeat = "yearly" if (body.get("repeat") or "") == "yearly" else ""
    ev = cal.add_event(date, title, body.get("time", ""), body.get("notes", ""), repeat,
                       body.get("prompt", ""))
    return ev


@router.delete("/api/events/{eid}")
def events_del(eid: str):
    return {"deleted": cal.remove_event(eid)}


# Tagebuch fuer den Kalender: an welchen Tagen in welchem Projektordner
# gearbeitet wurde. Nicht als Termine gespeichert, sondern aus den Transkripten
# abgeleitet — so ist auch alles da, was VOR dieser Funktion lief, und nichts
# kann auseinanderlaufen. Gezaehlt werden nur echte Eingaben (keine Tool-
# Ergebnisse, keine System-Wrapper); ein Tag gehoert zur ORTSZEIT, nicht UTC.
# Pro Datei gecacht nach (mtime, size): ganze Transkripte zu lesen ist teuer,
# und die meisten aendern sich zwischen zwei Kalenderaufrufen nicht.
_ACTIVITY_CACHE: dict = {}


def _day_of(ts: str) -> str:
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return ""


def _file_activity(f: Path) -> dict:
    """{"title", "agent", "days": {tag: {cwd: anzahl Eingaben}}} einer .jsonl."""
    st = f.stat()
    key = (st.st_mtime, st.st_size)
    hit = _ACTIVITY_CACHE.get(f)
    if hit and hit[0] == key:
        return hit[1]
    days: dict = {}
    title, firma, cwd = None, "", None
    with f.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            # Schnellfilter vor json.loads: der Grossteil der Zeilen sind
            # Assistant-Antworten und Tool-Ergebnisse.
            if '"type":"user"' not in line and '"type":"attachment"' not in line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if not firma:
                firma = _fremde_firma(ev)
            if ev.get("type") != "user" or ev.get("isSidechain") or ev.get("isMeta"):
                continue
            if isinstance(ev.get("cwd"), str):
                cwd = ev["cwd"]
            txt = extract_text(ev.get("message", {}).get("content")).strip()
            if not txt or txt.startswith("<") or txt.startswith("Caveat"):
                continue
            if title is None:
                title = txt.replace("\n", " ")[:80]
            day = _day_of(ev.get("timestamp") or "")
            if day and cwd and not _verborgen(cwd):
                per = days.setdefault(day, {})
                per[cwd] = per.get(cwd, 0) + 1
    res = {"title": title, "agent": firma, "days": days}
    _ACTIVITY_CACHE[f] = (key, res)
    return res


@router.get("/api/activity")
def activity(start: str = "", end: str = ""):
    """Projekte je Tag im Bereich [start, end] (YYYY-MM-DD, beide inklusive):
    {tag: [{"cwd", "n", "sessions": [{"id", "project", "cwd", "title", "n"}]}]}
    Sessions fremder Agenten-Anwendungen (FREMDE_MCP) zaehlen nicht mit."""
    from datetime import datetime
    out: dict = {}
    names = load_meta().get("names", {})

    def add(day, cwd, sess, n):
        if (start and day < start) or (end and day > end):
            return
        projs = out.setdefault(day, {})
        p = projs.setdefault(cwd, {"cwd": cwd, "n": 0, "sessions": []})
        p["n"] += n
        p["sessions"].append({**sess, "cwd": cwd, "n": n})

    if PROJECTS_DIR.exists():
        for f in PROJECTS_DIR.glob("*/*.jsonl"):
            try:
                a = _file_activity(f)
            except Exception:
                continue
            if a["agent"]:
                continue
            sess = {"id": f.stem, "project": f.parent.name,
                    "title": names.get(f.stem) or a["title"] or "(ohne Titel)"}
            for day, per in a["days"].items():
                for cwd, n in per.items():
                    add(day, cwd, sess, n)
    # Externe Modelle kennen keine Zeitstempel pro Nachricht — dort zaehlt der
    # Tag der letzten Aenderung.
    for s in llmmod.list_sessions() + hermesmod.list_sessions():
        try:
            day = datetime.fromtimestamp(s["mtime"]).strftime("%Y-%m-%d")
        except Exception:
            continue
        add(day, s.get("cwd") or "(unbekannt)",
            {"id": s["id"], "project": s["project"], "title": names.get(s["id"]) or s["title"]}, 1)
    return {day: sorted(projs.values(), key=lambda p: -p["n"]) for day, projs in out.items()}
