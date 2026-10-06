"""API: Ordner, Skills, MCP-Server, Datei-Vorschau und Uploads."""
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from server import attach
from server import config as cfg

from server.core import WORKSPACE, claude_bin, claude_env

router = APIRouter()


# Woran ein Projekt zu erkennen ist. Ordner OHNE eine dieser Dateien, die aber
# Unterordner haben, gelten als Sammelordner (z.B. ~/Projekte/Firma/kunden) —
# in die kann man in der Ordner-Auswahl hineinklicken.
PROJECT_MARKERS = (
    ".git", "CLAUDE.md", "AGENTS.md", "README.md", "package.json", "composer.json",
    "pubspec.yaml", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "Makefile", "index.html", "index.php", "artisan",
)
# Nie als Projekt anbieten — Abhängigkeiten, Build-Ausgaben, Umgebungen.
SKIP_DIRS = {"node_modules", "vendor", "__pycache__", "venv", "dist", "build", "target"}
TREE_MAX_DEPTH = 4
TREE_MAX_NODES = 1500


def _subdirs(path):
    try:
        with os.scandir(path) as it:
            dirs = [e for e in it if e.is_dir() and not e.name.startswith(".")
                    and e.name not in SKIP_DIRS and not e.name.startswith(".venv")]
    except OSError:
        return []
    return sorted(dirs, key=lambda e: e.name.lower())


def _is_project(path):
    return any(os.path.exists(os.path.join(path, m)) for m in PROJECT_MARKERS)


def folder_tree(root=None):
    """Ordnerbaum unter WORKSPACE. Projekte werden nicht weiter aufgeklappt
    (sonst landen android/, lib/, src/ … in der Auswahl), nur Sammelordner."""
    root = root or WORKSPACE
    budget = [TREE_MAX_NODES]

    def walk(path, depth):
        kids = []
        for e in _subdirs(path):
            if budget[0] <= 0:
                break
            budget[0] -= 1
            project = _is_project(e.path)
            node = {"path": e.path, "name": e.name, "project": project, "children": []}
            if not project and depth < TREE_MAX_DEPTH:
                node["children"] = walk(e.path, depth + 1)
            kids.append(node)
        return kids

    return {"path": root, "name": os.path.basename(root.rstrip(os.sep)) or root,
            "project": False, "children": walk(root, 1)}


@router.get("/api/folders")
def folders():
    """Alle wählbaren Ordner flach, WORKSPACE zuerst (für /folder im Chat)."""
    out = []

    def flat(node):
        out.append(node["path"])
        for c in node["children"]:
            flat(c)

    flat(folder_tree())
    return out


@router.get("/api/folders/tree")
def folders_tree():
    """Ordnerbaum für die Ordner-Auswahl über dem Chat."""
    return folder_tree()


def _parse_skill_md(path):
    name = os.path.basename(os.path.dirname(path))
    desc = ""
    try:
        txt = Path(path).read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^---\s*(.*?)\s*---", txt, re.S | re.M)
        fm = m.group(1) if m else txt[:500]
        nm = re.search(r"^name:\s*(.+)$", fm, re.M)
        dm = re.search(r"^description:\s*(.+)$", fm, re.M)
        if nm:
            name = nm.group(1).strip().strip("\"'")
        if dm:
            desc = dm.group(1).strip().strip("\"'")[:160]
    except Exception:
        pass
    return name, desc


GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"


@router.get("/api/skills")
def skills():
    """Sammelt Skills: global (~/.claude/skills) + aus allen Projekten."""
    groups = {}
    # Globale, projektübergreifende Skills zuerst (das Hermes-Gedächtnis von Cody)
    if GLOBAL_SKILLS_DIR.is_dir():
        gitems = []
        for d in sorted(os.listdir(GLOBAL_SKILLS_DIR), key=str.lower):
            md = GLOBAL_SKILLS_DIR / d / "SKILL.md"
            if md.is_file():
                nm, desc = _parse_skill_md(str(md))
                gitems.append({"name": nm, "desc": desc, "path": str(md), "kind": "md"})
        if gitems:
            groups[cfg.L("★ global (alle Projekte)", "★ global (all projects)")] = gitems
    if not os.path.isdir(WORKSPACE):
        return groups
    for proj in sorted(os.listdir(WORKSPACE), key=str.lower):
        pdir = os.path.join(WORKSPACE, proj)
        if not os.path.isdir(pdir) or proj.startswith("."):
            continue
        items = []
        for skroot in (os.path.join(pdir, ".claude", "skills"),
                       os.path.join(pdir, ".agents", "skills")):
            if os.path.isdir(skroot):
                for d in sorted(os.listdir(skroot), key=str.lower):
                    md = os.path.join(skroot, d, "SKILL.md")
                    if os.path.isfile(md):
                        nm, desc = _parse_skill_md(md)
                        items.append({"name": nm, "desc": desc, "path": md, "kind": "md"})
        pyroot = os.path.join(pdir, "skills")
        if os.path.isdir(pyroot):
            for fn in sorted(os.listdir(pyroot), key=str.lower):
                if fn.endswith(".py") and not fn.startswith("_"):
                    items.append({"name": fn[:-3], "desc": "(Python-Skill)",
                                  "path": os.path.join(pyroot, fn), "kind": "py"})
        if items:
            groups[proj] = items
    return groups


@router.get("/api/skill")
def skill_file(path: str):
    rp = os.path.realpath(path)
    roots = [os.path.realpath(WORKSPACE), os.path.realpath(str(GLOBAL_SKILLS_DIR))]
    # os.sep anhängen -> ~/projects2 zählt nicht als "unter ~/projects"
    if not any(rp == r or rp.startswith(r + os.sep) for r in roots) or not os.path.isfile(rp):
        return JSONResponse({"error": "not allowed"}, status_code=403)
    try:
        content = Path(rp).read_text(encoding="utf-8", errors="replace")[:30000]
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"path": rp, "content": content}


# ---------- Datei-Vorschau / Download (Pfade in Codys Antworten anklickbar) ----------
MAX_FILE_SERVE = 200 * 1024 * 1024


@router.get("/api/file")
def file_get(path: str, dl: int = 0):
    """Liefert eine Datei aus dem Workspace aus. Dotfiles (.env, .oauth-token, …)
    und alles außerhalb des Workspace sind tabu."""
    rp = os.path.realpath(path)
    root = os.path.realpath(WORKSPACE)
    if not (rp == root or rp.startswith(root + os.sep)):
        return JSONResponse({"error": "nur Dateien im Workspace"}, status_code=403)
    rel = os.path.relpath(rp, root)
    if any(part.startswith(".") for part in rel.split(os.sep)):
        return JSONResponse({"error": "versteckte Dateien sind tabu"}, status_code=403)
    if not os.path.isfile(rp):
        return JSONResponse({"error": "keine Datei"}, status_code=404)
    if os.path.getsize(rp) > MAX_FILE_SERVE:
        return JSONResponse({"error": "Datei zu groß"}, status_code=400)
    fname = os.path.basename(rp)
    if dl:
        return FileResponse(rp, filename=fname)
    # Unbekannte Typen als text/plain inline zeigen statt Download zu erzwingen
    import mimetypes
    mt = mimetypes.guess_type(fname)[0] or "text/plain; charset=utf-8"
    return FileResponse(rp, media_type=mt,
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})


def _mcp_kachel_an():
    """Wie bei den Tickets: ist die Kachel aus, gibt es die Routen nicht."""
    if not cfg.load_settings()["tiles"].get("mcp"):
        raise HTTPException(status_code=404, detail="MCP-Kachel ist abgeschaltet")


@router.get("/api/mcp", dependencies=[Depends(_mcp_kachel_an)])
def mcp():
    """Liste der konfigurierten MCP-Server / Konnektoren (via `claude mcp list`)."""
    try:
        out = subprocess.run(
            [claude_bin() or "claude", "mcp", "list"],
            capture_output=True, text=True, timeout=30, cwd=WORKSPACE,
            env=claude_env(),
        ).stdout
    except Exception as e:
        return {"servers": [], "error": str(e)}
    servers = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("checking"):
            continue
        if ": " in line and " - " in line:
            name, rest = line.split(": ", 1)
            url, status = rest.rsplit(" - ", 1)
            low = status.lower()
            servers.append({
                "name": name.strip(),
                "url": url.strip(),
                "status": status.strip(),
                "ok": ("✔" in status) or ("connected" in low) or ("✓" in status),
                "needs_auth": "auth" in low,
            })
    return {"servers": servers}


# Einrichten und Entfernen laufen über die CLI statt über ~/.claude.json direkt:
# die Datei gehört Claude Code, und deren Aufbau ändert sich zwischen Versionen.
# Der Name darf nicht mit "-" anfangen, sonst liest die CLI ihn als Schalter.
MCP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MCP_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
MCP_HEADER_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,128}$")
MCP_SCOPES = ("user", "local")
MCP_TRANSPORTS = ("stdio", "http", "sse")
MCP_TIMEOUT = 30


def _bad(msg: str):
    return HTTPException(status_code=400, detail=msg)


def _str_map(val, key_re, what: str) -> dict:
    if val in (None, ""):
        return {}
    if not isinstance(val, dict) or len(val) > 50:
        raise _bad(f"{what}: erwartet werden höchstens 50 Paare aus Name und Wert.")
    for k, v in val.items():
        if not isinstance(k, str) or not key_re.fullmatch(k):
            # Nur der Schlüssel landet in der Meldung, der Wert kann geheim sein.
            raise _bad(f"{what}: ungültiger Name „{str(k)[:64]}“.")
        if not isinstance(v, str) or len(v) > 8192 or any(c in v for c in "\r\n\0"):
            raise _bad(f"{what}: der Wert zu „{k}“ ist ungültig (Text ohne Zeilenumbruch).")
    return dict(val)


def _check_scope(scope) -> str:
    if scope not in MCP_SCOPES:
        raise _bad("Bereich muss „user“ oder „local“ sein.")
    return scope


def _check_name(name) -> str:
    if not isinstance(name, str) or not MCP_NAME_RE.fullmatch(name):
        raise _bad("Name: nur Buchstaben, Ziffern, - und _, höchstens 64 Zeichen, "
                   "am Anfang kein - oder _.")
    return name


def _mcp_config(p: dict) -> tuple[dict, list[str]]:
    """Prüft die Eingabe und baut das JSON für `claude mcp add-json`.

    Liefert dazu die Werte, die in keiner Meldung auftauchen dürfen."""
    transport = p.get("transport") or "stdio"
    if transport not in MCP_TRANSPORTS:
        raise _bad("Art muss „stdio“, „http“ oder „sse“ sein.")
    if transport == "stdio":
        command = p.get("command")
        if not isinstance(command, str) or not command.strip() \
                or len(command) > 1024 or "\0" in command:
            raise _bad("Für stdio fehlt der Befehl.")
        args = p.get("args") or []
        if not isinstance(args, list) or len(args) > 100 or not all(
                isinstance(a, str) and len(a) <= 4096 and "\0" not in a for a in args):
            raise _bad("Argumente: erwartet wird eine Liste aus Texten.")
        env = _str_map(p.get("env"), MCP_ENV_KEY_RE, "Umgebungsvariablen")
        conf = {"type": "stdio", "command": command.strip(), "args": args}
        if env:
            conf["env"] = env
        return conf, list(env.values())
    url = p.get("url")
    if not isinstance(url, str) or len(url) > 2048:
        raise _bad(f"Für {transport} fehlt die URL.")
    url = url.strip()
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc \
            or any(c.isspace() for c in url):
        raise _bad("Die URL muss mit http:// oder https:// beginnen.")
    headers = _str_map(p.get("headers"), MCP_HEADER_RE, "Header")
    conf = {"type": transport, "url": url}
    if headers:
        conf["headers"] = headers
    return conf, list(headers.values())


def _run_mcp(args: list[str]) -> subprocess.CompletedProcess:
    exe = claude_bin()
    if not exe:
        raise HTTPException(status_code=502, detail="Claude Code ist nicht installiert.")
    try:
        # cwd = WORKSPACE wie bei der Liste: darauf bezieht sich der Bereich "local".
        return subprocess.run([exe, "mcp", *args], capture_output=True, text=True,
                              timeout=MCP_TIMEOUT, cwd=WORKSPACE, env=claude_env())
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504,
                            detail="Claude Code hat nicht rechtzeitig geantwortet.")
    except OSError as e:
        raise HTTPException(status_code=502,
                            detail=f"Claude Code ließ sich nicht starten ({e.strerror}).")


def _cli_error(res: subprocess.CompletedProcess, secrets: list[str]) -> str:
    """Kurzfassung der CLI-Meldung, Geheimnisse geschwärzt.

    Längste zuerst, damit ein kurzer Wert nicht einen längeren nur zur Hälfte
    schwärzt. Erst schwärzen, dann trimmen: sonst fehlt einem Geheimnis mit
    Leerzeichen am Ende genau dieses und es passt nicht mehr."""
    text = res.stderr if (res.stderr or "").strip() else (res.stdout or "")
    for s in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(s, "***")
    text = " ".join(text.split())  # trimmt auch
    return text[:300] or f"Exit-Code {res.returncode}"


@router.post("/api/mcp", dependencies=[Depends(_mcp_kachel_an)])
def mcp_add(payload: Any = Body(None)):
    """MCP-Server für Claude Code einrichten (via `claude mcp add-json`).

    Ein JSON-Argument statt einzelner -e/-H-Schalter: die CLI muss dann kein
    KEY=Wert bzw. "Name: Wert" zerlegen, und Werte mit = oder : kommen
    unverändert an."""
    if not isinstance(payload, dict):
        raise _bad("Erwartet wird ein JSON-Objekt.")
    name = _check_name(payload.get("name"))
    scope = _check_scope(payload.get("scope") or "user")
    conf, secrets = _mcp_config(payload)
    raw = json.dumps(conf)
    res = _run_mcp(["add-json", name, raw, "-s", scope])
    if res.returncode != 0:
        # Auch die JSON-maskierte Form: so stünde ein Wert mit " oder \ im Echo.
        msg = _cli_error(res, secrets + [json.dumps(v)[1:-1] for v in secrets] + [raw])
        if "already exists" in msg:
            raise _bad(f"Einen Server „{name}“ gibt es im Bereich {scope} schon.")
        raise HTTPException(status_code=502, detail=f"Claude Code meldet: {msg}")
    return {"ok": True}


@router.delete("/api/mcp/{name}", dependencies=[Depends(_mcp_kachel_an)])
def mcp_remove(name: str, scope: str | None = None):
    """MCP-Server entfernen. Ohne scope sucht die CLI ihn in allen Bereichen."""
    _check_name(name)
    args = ["remove", name]
    if scope:
        args += ["-s", _check_scope(scope)]
    res = _run_mcp(args)
    if res.returncode != 0:
        msg = _cli_error(res, [])
        if "No MCP server named" in msg:
            where = f" im Bereich {scope}" if scope else ""
            raise HTTPException(status_code=404,
                                detail=f"Kein MCP-Server „{name}“{where} gefunden.")
        raise HTTPException(status_code=502, detail=f"Claude Code meldet: {msg}")
    return {"ok": True}


@router.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    data = await file.read()
    try:
        return attach.store(data, ext, file.filename or "")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
