"""API: Ordner, Skills, MCP-Server, Datei-Vorschau und Uploads."""
import os
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
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


@router.get("/api/mcp")
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


@router.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    data = await file.read()
    try:
        return attach.store(data, ext, file.filename or "")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
