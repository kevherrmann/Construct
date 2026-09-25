"""API: Session-Liste, Verlauf, Live-Tail, Umbenennen, Archiv, Löschen."""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import hermes as hermesmod
import llm as llmmod

from server.core import PROJECTS_DIR, extract_text
from server.sessions import SID_RE, _fremde_firma, _last_model, _parse_transcript_lines, _verborgen, load_archived, load_meta, save_archived, save_meta

router = APIRouter()


@router.get("/api/sessions")
def sessions():
    """Listet alle Claude-Code-Sessions (eine .jsonl-Datei = eine Session)
    plus die Sessions externer Modelle (llm_sessions/).

    Jeder Eintrag traegt ein Feld `agent`: leer bei Kevins eigenen Gespraechen,
    sonst der Name der Anwendung, die den Lauf gestartet hat (siehe
    FREMDE_MCP). Gefiltert wird nicht hier, sondern in der Oberflaeche — weg
    ist weg, und manchmal will man doch nachsehen, was die Firma getrieben hat.
    """
    out = []
    meta = load_meta()
    archived = set(meta.get("archived", []))
    names = meta.get("names", {})
    for s in llmmod.list_sessions() + hermesmod.list_sessions():
        s["title"] = names.get(s["id"]) or s["title"]
        s["renamed"] = s["id"] in names
        s["archived"] = s["id"] in archived
        out.append(s)
    if not PROJECTS_DIR.exists():
        return out
    for f in PROJECTS_DIR.glob("*/*.jsonl"):
        try:
            stat = f.stat()
            title = None
            cwd = None
            firma = ""
            # Nur die ersten paar Zeilen lesen reicht für Titel + cwd (Performance!)
            with f.open(encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i > 60 or (title and cwd and firma):
                        break
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if not firma:
                        firma = _fremde_firma(ev)
                    if cwd is None and isinstance(ev.get("cwd"), str):
                        cwd = ev["cwd"]
                    if title is None and ev.get("type") == "user":
                        txt = extract_text(ev.get("message", {}).get("content")).strip()
                        # System-/Befehls-Wrapper überspringen
                        if txt and not txt.startswith("<") and not txt.startswith("Caveat"):
                            title = txt.replace("\n", " ")[:80]
            if _verborgen(cwd or ""):
                continue
            out.append({
                "id": f.stem,
                "project": f.parent.name,
                "cwd": cwd or "(unbekannt)",
                "title": names.get(f.stem) or title or "(ohne Titel)",
                "renamed": f.stem in names,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "archived": f.stem in archived,
                "agent": firma,
            })
        except Exception:
            continue
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


@router.get("/api/sessions/{project}/{sid}")
def session_detail(project: str, sid: str):
    if project == "llm":
        s = llmmod.load_session(sid)
        if not s:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"id": sid, "project": "llm", "offset": 0,
                "model": f"{s.get('provider', '')}:{s.get('model', '')}",
                "messages": llmmod.session_display(s)}
    if project == "hermes":
        # sid kommt mit Präfix aus der Liste; die Datenbank kennt es ohne.
        raw = sid[len("hermes-"):] if sid.startswith("hermes-") else sid
        msgs = hermesmod.session_messages(raw)
        if not msgs:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"id": "hermes-" + raw, "project": "hermes", "offset": 0,
                "model": "", "messages": msgs}
    f = PROJECTS_DIR / project / f"{sid}.jsonl"
    if not f.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    data = f.read_bytes()
    # offset = Dateigröße beim Lesen -> Startpunkt für den Live-Tail der UI
    return {"id": sid, "project": project, "offset": len(data),
            "model": _last_model(data),
            "messages": _parse_transcript_lines(data)}


@router.get("/api/session_tail/{sid}")
def session_tail(sid: str, offset: int = -1):
    """Live-Tail: alles NEUE in der Session-Datei seit `offset` (Byte-Position).
    So sieht die UI auch Sessions wachsen, die woanders laufen (Terminal etc.)."""
    if sid.startswith("llm-"):
        # externe Sessions wachsen nur durch eigene Läufe -> nichts zu tailen
        return {"offset": 0, "messages": []}
    if not SID_RE.match(sid):
        return JSONResponse({"error": "bad id"}, status_code=400)
    f = next(iter(PROJECTS_DIR.glob(f"*/{sid}.jsonl")), None)
    if f is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    size = f.stat().st_size
    if offset < 0 or offset >= size:
        # nur synchronisieren (oder Datei wurde neu geschrieben/kleiner)
        return {"offset": size, "messages": []}
    with f.open("rb") as fh:
        fh.seek(offset)
        data = fh.read()
    # halbe letzte Zeile (wird gerade geschrieben) NICHT konsumieren
    if not data.endswith(b"\n"):
        cut = data.rfind(b"\n") + 1
        data, size = data[:cut], offset + cut
    return {"offset": size, "messages": _parse_transcript_lines(data)}


@router.post("/api/sessions/{sid}/archive")
async def session_archive(sid: str, req: Request):
    """Session aus-/einblenden (archivieren) — Datei bleibt erhalten."""
    body = await req.json()
    ids = load_archived()
    if body.get("archived"):
        ids.add(sid)
    else:
        ids.discard(sid)
    save_archived(ids)
    return {"id": sid, "archived": sid in ids}


@router.post("/api/sessions/{sid}/rename")
async def session_rename(sid: str, req: Request):
    """Eigenen Namen vergeben (leer = zurück zum automatischen Titel)."""
    body = await req.json()
    name = (body.get("name") or "").strip()[:120]
    meta = load_meta()
    names = meta.setdefault("names", {})
    if name:
        names[sid] = name
    else:
        names.pop(sid, None)
    save_meta(meta)
    return {"id": sid, "name": name}


@router.delete("/api/sessions/{project}/{sid}")
def session_delete(project: str, sid: str):
    """Session-Datei endgültig löschen (mit Pfad-Schutz)."""
    if project == "llm":
        if not llmmod.delete_session(sid):
            return JSONResponse({"error": "not found"}, status_code=404)
    elif project == "hermes":
        raw = sid[len("hermes-"):] if sid.startswith("hermes-") else sid
        if not hermesmod.delete_session(raw):
            return JSONResponse({"error": "not found"}, status_code=404)
    else:
        f = PROJECTS_DIR / project / f"{sid}.jsonl"
        try:
            rp = f.resolve()
            if rp.parent.parent != PROJECTS_DIR.resolve():
                return JSONResponse({"error": "not allowed"}, status_code=403)
        except Exception:
            return JSONResponse({"error": "bad path"}, status_code=400)
        if not rp.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        rp.unlink()
    meta = load_meta()
    changed = False
    if sid in meta.get("archived", []):
        meta["archived"].remove(sid)
        changed = True
    if meta.get("names", {}).pop(sid, None) is not None:
        changed = True
    if changed:
        save_meta(meta)
    return {"deleted": True, "id": sid}
