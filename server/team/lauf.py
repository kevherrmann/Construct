"""Einen claude-Lauf für die Firma bauen und starten.

Die Run-Engine selbst (Ereignisse puffern, Kosten lesen, Prozess beenden) ist die
von CONSTRUCT (server/runs.py) — ein Zug in einem Auftrag ist ein Lauf wie jeder
andere und lässt sich deshalb auch über /api/stream/<run_id> mitlesen.
"""
import asyncio
import uuid

from server.core import claude_bin
from server.runs import RUNS, Run, gc_runs, run_claude


def build_claude_cmd(*, mode, model="", session_id=None, system_prompt="",
                     system_prompt_file=None, allowed_tools=None, effort="",
                     mcp_config=None, intern=False, tools=None):
    """Die Kommandozeile fuer einen claude-Lauf — eine Stelle, zwei Aufrufer.

    Der Systemprompt geht als DATEI hinein, nicht als Argument: Rollenprompts
    werden lang, und argv ist in `ps` fuer jeden auf dem Rechner lesbar.

    tools: die eingebauten Werkzeuge, die es UEBERHAUPT gibt (--tools). Das ist die
    Sperre. --allowedTools gibt nur ohne Rueckfrage frei; was dort fehlt, entscheidet
    der Modus, und unter auto/bypassPermissions lief damit Bash bei der Chefin und
    WebFetch bei Janus (Janus' Probe gegen echtes claude, 06.10.2026). MCP-Werkzeuge
    (der Bus) sind davon nicht betroffen.

    intern=True ist fuer Laeufe, die nur DENKEN sollen (Verdichten, Eindicken,
    Kandidatensuche): keine eingebauten Werkzeuge, keine fremden MCP-Server.
    Ohne das laedt `claude -p` Kevins persoenliche MCP-Server aus ~/.claude.json
    mit — ein Gedaechtnis-Eindicken im Plan-Modus haette dann Zugriff auf
    dessen E-Mail-Anbindung, und der Start dauert laenger.
    """
    cmd = [
        claude_bin() or "claude", "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",   # Nachricht via stdin -> Inject möglich
        "--verbose",
        "--include-partial-messages",
        "--permission-mode", mode,
        # Ohne das laedt `claude -p` gar keine Projekt-Settings — und damit auch
        # nicht die Firmen-Skills unter <workspace>/.claude/skills/.
        "--setting-sources", "project",
    ]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    if system_prompt_file:
        cmd += ["--append-system-prompt-file", str(system_prompt_file)]
    elif system_prompt:
        cmd += ["--append-system-prompt", system_prompt]
    if mcp_config:
        # --strict-mcp-config: der Agent sieht NUR unseren Bus, nicht Kevins
        # persoenlich eingerichtete MCP-Server.
        cmd += ["--mcp-config", mcp_config, "--strict-mcp-config"]
    elif intern:
        # Ohne --mcp-config heisst strict: gar keine MCP-Server. Und "" bei
        # --tools schaltet die eingebauten ab (geprueft mit 2.1.260).
        cmd += ["--strict-mcp-config", "--tools", ""]
    if tools is not None and not intern:
        # "" heisst: keine eingebauten Werkzeuge
        cmd += ["--tools", ",".join(tools)]
    if allowed_tools:
        cmd += ["--allowedTools"] + list(allowed_tools)
    if session_id:
        cmd += ["--resume", session_id]
    return cmd


def spawn(cmd, work_dir, model, prompt, session_id=None, agent_slug="",
          auftrag_id="", bus_token=""):
    gc_runs()
    run_id = uuid.uuid4().hex
    run = Run(run_id, work_dir, session_id, model, initial_prompt=prompt)
    run.agent_slug = agent_slug
    run.auftrag_id = auftrag_id
    run.bus_token = bus_token
    # Alles setzen, BEVOR der Prozess laeuft: sonst kann ein sehr frueher
    # Werkzeugaufruf gezaehlt und unmittelbar danach wieder ueberschrieben
    # werden — ein Wettlauf, den man erst bei schnellen Modellen bemerkt.
    RUNS[run_id] = run
    run.task = asyncio.create_task(run_claude(run, cmd))
    return run
