"""Hermes Agent als Werkzeug-Backend für fremde Modelle.

Warum überhaupt: `claude -p` kann Dateien und Terminal, aber nur mit einem
Anthropic-Konto. Reine Chat-Anbindungen (llm.py) können jedes Modell, aber
keine Werkzeuge. Hermes schließt die Lücke — ein Agenten-Framework, das die
Werkzeugschleife für beliebige OpenAI-kompatible Modelle fährt, inklusive
lokaler über Ollama.

Gesprochen wird **ACP** (Agent Client Protocol) über stdin/stdout des
Unterprozesses `hermes acp`. Das ist bewusst dieselbe Form, in der app.py
schon `claude -p --output-format stream-json` fährt: ein Prozess, Zeilen mit
JSON, kein Server, kein Port, kein Token. Editoren wie Zed sprechen dasselbe
Protokoll, es ist also keine Sonderlocke für uns.

Aufrufreihenfolge (die Namen stammen aus dem ACP-Schema, nicht geraten):
    initialize → session/new {cwd} → session/set_model → session/prompt
    ← session/update  (agent_message_chunk, agent_thought_chunk, tool_call …)
    → session/cancel  (Stop-Knopf)
"""
import asyncio
import json
import os
import re
import shutil
import threading
import time
import urllib.request
from pathlib import Path

from server import bonsai as bonsaimod
from server import llm as llmmod

# Liegt in server/ — Daten und Einstellungen bleiben im Projektordner darüber.
BASE_DIR = Path(__file__).resolve().parent.parent

# Die offizielle Installationsroutine. Wird nur nach ausdrücklichem Klick in
# den Einstellungen ausgeführt — nichts davon passiert von allein.
INSTALL_URL = "https://hermes-agent.nousresearch.com/install.sh"


def hermes_bin() -> str:
    """Pfad zum hermes-CLI, oder "" wenn es nicht installiert ist.

    Über shutil.which statt eines festen Pfads: die Installationsroutine legt
    den Aufruf-Wrapper je nach System nach ~/.local/bin, /usr/local/bin oder
    ins Termux-Präfix. which() wertet außerdem PATHEXT aus, was unter Windows
    nötig ist.
    """
    return shutil.which("hermes") or ""


def hermes_home() -> str:
    """HERMES_HOME für Unterprozesse.

    Vorrang hat die Umgebung, dann die Einstellung, dann der Standard des
    Installers. Konfigurierbar, weil ~/.hermes bereits belegt sein kann —
    etwa von einem Container, der unter fremder Benutzerkennung lief.
    """
    env = os.environ.get("HERMES_HOME", "").strip()
    if env:
        return env
    try:
        from server import config as cfg
        p = (cfg.load_settings().get("hermes") or {}).get("home", "").strip()
        if p:
            return os.path.expanduser(p)
    except Exception:
        pass
    return str(Path.home() / ".hermes")


def version() -> str:
    if not hermes_bin():
        return ""
    try:
        import subprocess
        out = subprocess.run([hermes_bin(), "--version"], capture_output=True,
                             text=True, timeout=20, env=child_env()).stdout
        return out.strip().splitlines()[0] if out.strip() else ""
    except Exception:
        return ""


def child_env() -> dict:
    """Umgebung für hermes-Unterprozesse.

    CONSTRUCT bleibt die eine Stelle, an der Schlüssel gepflegt werden: die
    aus .llm-config.json werden hier in die Variablennamen übersetzt, die
    Hermes erwartet. Zwei getrennte Schlüsselverwaltungen wären genau die
    Sorte Doppelpflege, bei der eine davon veraltet.
    """
    env = dict(os.environ)
    env["HERMES_HOME"] = hermes_home()
    # Ohne das fragt der Agent beim ersten unbekannten Shell-Hook auf einem
    # Terminal nach, das es hier nicht gibt — der Lauf bliebe stehen.
    env["HERMES_ACCEPT_HOOKS"] = "1"
    for pid, var in (("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY"),
                     ("deepseek", "DEEPSEEK_API_KEY")):
        key = llmmod.provider_conf(pid).get("api_key") or ""
        if key:
            env[var] = key
    return env


# ---------- Persona und Kalender für fremde Modelle ----------
# Claude bekommt SOUL.md/USER.md und den Kalender bei jedem Lauf per
# --append-system-prompt. Hermes kennt dafür keinen Schalter, lädt aber
# $HERMES_HOME/SOUL.md als Identität — und friert den System-Prompt beim
# Start einer Sitzung ein. Also: der feste Teil (Persona, Sprache) wandert in
# SOUL.md, der Kalender (ändert sich laufend) geht mit jeder Nachricht mit.
SOUL_MARK = ("<!-- Von CONSTRUCT geschrieben (SOUL.md + USER.md aus ⚙ Persona). "
             "Änderungen bitte dort — diese Datei wird überschrieben. -->")
HERMES_DEFAULT_SOUL = "You are Hermes Agent, built by Nous Research."
CTX_OPEN, CTX_CLOSE = "[CONSTRUCT-Kontext]", "[/CONSTRUCT-Kontext]"
_CTX_RE = re.compile(r"\s*" + re.escape(CTX_OPEN) + r".*?" + re.escape(CTX_CLOSE) + r"\s*$",
                     re.S)


def sync_soul() -> bool:
    """$HERMES_HOME/SOUL.md auf die CONSTRUCT-Persona bringen.

    Überschrieben wird nur, was fehlt, von Hermes vorgegeben ist oder von uns
    stammt — eine SOUL.md, die jemand für Hermes selbst geschrieben hat,
    bleibt unangetastet. True = die Datei trägt jetzt unsere Persona."""
    from server.core import persona_text
    path = Path(hermes_home()) / "SOUL.md"
    want = f"{SOUL_MARK}\n\n{persona_text()}\n"
    try:
        have = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        have = ""
    except OSError:
        return False
    if have == want:
        return True
    if have.strip() and SOUL_MARK not in have \
            and not have.lstrip().startswith(HERMES_DEFAULT_SOUL):
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(want, encoding="utf-8")
        path.chmod(0o600)
    except OSError:
        return False
    return True


def with_context(prompt: str) -> str:
    """Kalender an die Nachricht hängen — markiert, damit die Verlaufsansicht
    ihn wieder abschneiden kann (strip_context)."""
    from server.core import calendar_text
    block = calendar_text()
    return f"{prompt}\n\n{CTX_OPEN}\n{block}\n{CTX_CLOSE}" if block else prompt


def strip_context(text: str) -> str:
    return _CTX_RE.sub("", text)


# ---------- Fehlermeldungen von Hermes ----------
# Scheitert ein Lauf am Anbieter (Limit, Key, Ausfall), schreibt Hermes das als
# gewöhnlichen Antworttext — auf Englisch, mehrzeilig und mit Ratschlägen für
# sein eigenes Terminal (/retry, /model, `hermes fallback add`), die in
# CONSTRUCT ins Leere gehen. Bekannte Fälle werden zu einem kurzen Hinweis;
# Unbekanntes bleibt, wie es ist. Vorlagen: agent/turn_failure_copy.py.
_FAIL_PATTERNS = [
    ("rate", re.compile(r"^(?P<label>.{1,60}?) rate-limited every one of \d+ attempts — ")),
    ("down", re.compile(r"^(?P<label>.{1,60}?) (?:reported it was overloaded on all|returned a "
                        r"server error on all|didn't respond in time on any of|didn't answer "
                        r"after) \d+ attempts — ")),
    ("key", re.compile(r"^(?P<label>.{1,60}?) rejected your (?:API key|sign-in), "
                       r"so the model can't be ")),
    ("model", re.compile(r"^Model '(?P<model>[^']+)' isn't available on (?P<label>.{1,60}?)\. ")),
]


def friendly_failure(text: str) -> str | None:
    """Hermes-Fehlertext → kurzer Hinweis (Markdown), sonst None."""
    from server import config as cfg
    head = text.lstrip()
    for kind, rx in _FAIL_PATTERNS:
        m = rx.match(head)
        if m:
            break
    else:
        return None
    label = m.group("label")
    if kind == "rate":
        msg = cfg.L(f"⚠ **Kontingent erschöpft** — {label} nimmt gerade keine weiteren "
                    "Anfragen an. Kurz warten und die Nachricht nochmal senden, oder oben ein "
                    "anderes Modell wählen.",
                    f"⚠ **Quota used up** — {label} is not accepting more requests right now. "
                    "Wait a moment and send the message again, or pick another model above.")
        reset = re.search(r"usage limit resets in ([^.]+)\.", head)
        if reset:
            msg += cfg.L(f" Das Limit wird in {reset.group(1)} zurückgesetzt.",
                         f" The limit resets in {reset.group(1)}.")
        if "free_tier" in head:
            msg += cfg.L("\n\nIm kostenlosen Kontingent ist bei Aufgaben mit Werkzeugen schnell "
                         "Schluss: jeder Werkzeug-Schritt ist eine eigene Anfrage. Die Lite-Modelle "
                         "haben mehr Luft.",
                         "\n\nThe free tier runs out quickly on tasks with tools: every tool step "
                         "is a request of its own. The Lite models have more headroom.")
    elif kind == "down":
        msg = cfg.L(f"⚠ **{label} antwortet gerade nicht** — später nochmal versuchen oder oben "
                    "ein anderes Modell wählen.",
                    f"⚠ **{label} is not responding right now** — try again later or pick "
                    "another model above.")
    elif kind == "key":
        msg = cfg.L(f"⚠ **{label} lehnt den Zugang ab** — Key unter ⚙ Einstellungen → "
                    "Modelle & Anbieter prüfen.",
                    f"⚠ **{label} rejected the credentials** — check the key under ⚙ Settings "
                    "→ Models & providers.")
    else:
        msg = cfg.L(f"⚠ **Modell „{m.group('model')}“ gibt es bei {label} nicht** — oben ein "
                    "anderes wählen.",
                    f"⚠ **Model '{m.group('model')}' is not available on {label}** — pick "
                    "another one above.")
    said = re.search(r"Provider said: (.+)", head)
    if said:
        detail = said.group(1).strip()
        msg += f"\n\n_Details: {detail[:240]}{'…' if len(detail) > 240 else ''}_"
    return msg


def acp_model_id(model: str) -> str:
    """CONSTRUCT-Wert "anbieter:modell" → Hermes-Modell-ID.

    Die eingebauten Anbieter (openai, ollama …) heißen bei Hermes genauso;
    Bonsai kennt es nur als selbst eingetragenen Endpunkt "custom:bonsai".
    """
    pid, m = llmmod.split_model(model)
    if pid == "bonsai":
        return bonsaimod.acp_model_id(m)
    return model


# ---------- Installation (nur auf Klick) ----------
_INSTALL = {"running": False, "done": True, "log": [], "error": "", "t": 0.0}
_INSTALL_LOCK = threading.Lock()


def install_state() -> dict:
    st = dict(_INSTALL)
    st["log"] = list(st["log"])[-40:]
    st["installed"] = bool(hermes_bin())
    st["version"] = version() if st["installed"] else ""
    return st


def install_start() -> dict:
    """Lädt install.sh und führt es aus — im Hintergrund, mit Protokoll.

    Zweistufig (erst laden, dann ausführen) statt `curl | bash`: so scheitert
    ein Netzfehler sichtbar, statt als leere Eingabe an eine Shell zu gehen,
    die dann brav mit Erfolg beendet.
    """
    with _INSTALL_LOCK:
        if _INSTALL["running"]:
            return {"ok": True, "already": True}
        _INSTALL.update(running=True, done=False, log=[], error="", t=time.time())

    def log(line: str):
        _INSTALL["log"].append(line.rstrip()[:400])

    def worker():
        import subprocess
        try:
            if os.name != "posix":
                raise RuntimeError(
                    "Die automatische Installation gibt es nur für Linux und macOS. "
                    "Unter Windows in PowerShell:  iex (irm "
                    "https://hermes-agent.nousresearch.com/install.ps1)")
            log("» Installationsroutine laden …")
            script = BASE_DIR / ".hermes-install.sh"
            with urllib.request.urlopen(INSTALL_URL, timeout=60) as r:
                data = r.read()
            if len(data) < 1000 or b"Hermes" not in data[:4000]:
                raise RuntimeError("Heruntergeladene Datei sieht nicht wie der "
                                   "Installer aus — abgebrochen.")
            script.write_bytes(data)
            log(f"» geladen ({len(data)//1024} KB), starte …")
            env = dict(os.environ, HERMES_HOME=hermes_home())
            proc = subprocess.Popen(
                ["bash", str(script), "--skip-setup"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env, cwd=str(BASE_DIR))
            for line in proc.stdout:
                line = line.strip()
                if line:
                    log(line)
            proc.wait()
            script.unlink(missing_ok=True)
            if proc.returncode != 0:
                raise RuntimeError(f"Installer beendet mit Code {proc.returncode}")
            if not hermes_bin():
                raise RuntimeError(
                    "Installer lief durch, aber 'hermes' ist nicht im PATH. "
                    "Meist hilft ein Neustart von CONSTRUCT.")
            log("✓ fertig")
        except Exception as e:
            _INSTALL["error"] = f"{type(e).__name__}: {e}"
            log("!! " + _INSTALL["error"])
        finally:
            _INSTALL.update(running=False, done=True)

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True}


# ---------- ACP-Client ----------
# Abbruch, wenn der Lauf so lange gar nichts mehr meldet UND kein Werkzeug
# offen ist (Werkzeuge dürfen beliebig lange still arbeiten). Schützt vor
# hängenden Anbieter-Verbindungen, ohne lange Builds zu killen.
IDLE_TIMEOUT = float(os.environ.get("HERMES_IDLE_TIMEOUT", "1200"))


class AcpError(Exception):
    """Verständlicher Fehler; wird dem Nutzer 1:1 angezeigt."""


class AcpSession:
    """Ein Lauf gegen `hermes acp`.

    Aufbau: EINE Hintergrund-Aufgabe liest stdout und verteilt. Antworten auf
    eigene Anfragen landen in Futures, alles Übrige in einer Warteschlange,
    die run() abarbeitet.

    Das ist nicht Geschmack, sondern notwendig: liest man erst nach dem Senden
    in der Hauptschleife, wartet `initialize` auf eine Antwort, die niemand
    abholt — der Lauf steht bis zum Zeitüberlauf. Genau so ist mir das beim
    ersten Versuch passiert.

    Ein Prozess pro Lauf, kein Pool: ein Prozess, der zwischen Läufen lebt,
    müsste Sitzungszustand, Abstürze und hängende Werkzeuge überleben — viel
    Maschinerie ohne Gegenwert bei Läufen von Sekunden bis Minuten.
    """

    def __init__(self, cwd: str, model: str = "", session_id: str = ""):
        self.cwd = cwd
        self.model = model            # "anbieter:modell", z.B. deepseek:deepseek-v4-flash
        self.session_id = session_id  # gesetzt = fortsetzen statt neu
        self.proc = None
        self._next_id = 0
        self._pending = {}            # JSON-RPC-id -> Future
        self._q = None                # Warteschlange für Mitteilungen/Anfragen
        self._stderr = []
        self._eof = False
        self._open_tools = []      # gestartet, aber noch ohne Abschlussmeldung

    # -- Prozess --
    async def start(self):
        if not hermes_bin():
            raise AcpError("Hermes ist nicht installiert. Unter ⚙ Einstellungen → "
                           "„Modelle & Anbieter“ lässt es sich einrichten.")
        if llmmod.split_model(self.model)[0] == "bonsai":
            # Hermes muss den Endpunkt kennen, bevor set_model ihn wählen kann.
            err = await asyncio.to_thread(bonsaimod.ensure_hermes_provider,
                                          hermes_bin(), child_env())
            if err:
                raise AcpError(err)
        self._q = asyncio.Queue()
        self.proc = await asyncio.create_subprocess_exec(
            hermes_bin(), "acp", "--accept-hooks",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd, env=child_env(),
            limit=64 * 1024 * 1024,   # große Werkzeug-Ergebnisse in einer Zeile
        )
        asyncio.create_task(self._reader())
        asyncio.create_task(self._drain_stderr())

    async def _reader(self):
        """Liest stdout und verteilt: Antworten in Futures, Rest in die Schlange."""
        try:
            while True:
                raw = await self.proc.stdout.readline()
                if not raw:
                    break
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue       # Fremdausgabe im Datenstrom ignorieren
                if "id" in msg and ("result" in msg or "error" in msg):
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        if "error" in msg:
                            e = msg["error"] or {}
                            fut.set_exception(AcpError(str(e.get("message") or e)))
                        else:
                            fut.set_result(msg.get("result"))
                    continue
                await self._q.put(msg)
        finally:
            self._eof = True
            # Wartende aufwecken, statt sie in den Zeitüberlauf laufen zu lassen
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(AcpError(
                        "Hermes hat sich beendet." +
                        ("\n" + self.stderr_text() if self.stderr_text() else "")))
            self._pending.clear()
            if self._q is not None:
                await self._q.put(None)

    async def _drain_stderr(self):
        # Muss mitgelesen werden, sonst blockiert der Prozess, sobald der
        # Puffer volläuft. Die letzten Zeilen sind im Fehlerfall die Erklärung.
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                break
            t = line.decode("utf-8", "replace").rstrip()
            if t and len(self._stderr) < 200:
                self._stderr.append(t)

    def stderr_text(self) -> str:
        # Nur echte Fehler, nicht das Startprotokoll (Plugin-Meldungen u.ä.)
        bad = [l for l in self._stderr if "[ERROR]" in l or "Traceback" in l
               or "Error" in l or "error:" in l.lower()]
        return "\n".join((bad or self._stderr)[-8:]).strip()

    # -- JSON-RPC --
    def _send(self, obj: dict):
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())

    async def call(self, method: str, params: dict, timeout: float = 120):
        self._next_id += 1
        rid = self._next_id
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        await self.proc.stdin.drain()
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            raise AcpError(f"Hermes antwortet nicht auf {method} (nach {int(timeout)} s)."
                           + ("\n" + self.stderr_text() if self.stderr_text() else ""))

    def notify(self, method: str, params: dict):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def reply(self, rid, result: dict):
        self._send({"jsonrpc": "2.0", "id": rid, "result": result})

    # -- Lauf: übersetzt ACP in die Ereignis-Sprache von CONSTRUCT --
    async def run(self, prompt: str, emit, allow_writes: bool = True, images=None):
        """Fährt einen Lauf und ruft emit(ereignis) für jedes Ereignis.

        Die Ereignisnamen sind dieselben, die run_claude schickt — das Frontend
        merkt keinen Unterschied zwischen den Maschinen dahinter.
        """
        await self.start()

        await self.call("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
        }, timeout=90)

        resumed = False
        if self.session_id:
            try:
                await self.call("session/load", {"sessionId": self.session_id,
                                                 "cwd": self.cwd, "mcpServers": []}, timeout=120)
                resumed = True
            except AcpError:
                # Sitzung nicht mehr ladbar (Hermes-Update, aufgeräumte Datenbank,
                # anderer Rechner): statt mit einem Fehler stehen zu bleiben, neue
                # Sitzung mit dem bisherigen Verlauf als Kontext — dieselbe
                # Ehrlichkeit wie beim Maschinenwechsel (carry_over_block).
                block = _history_fallback(self.session_id)
                self.session_id = ""
                if block:
                    prompt = block + "\n\n" + prompt
                emit({"type": "text", "text":
                      "_↪ Die bisherige Hermes-Sitzung ließ sich nicht fortsetzen — "
                      "neue Sitzung, bisheriger Verlauf als Kontext übernommen._\n\n"})
        if resumed:
            # Beim Fortsetzen spielt Hermes den bisherigen Verlauf noch einmal
            # als session/update in den Strom. Ungefiltert erschiene die alte
            # Antwort als neue — sichtbar als vorangestellter Textblock, den
            # niemand angefordert hat. Alles, was VOR unserem Prompt eintrifft,
            # ist Wiederholung und wird verworfen.
            dropped = 0
            while True:
                try:
                    if self._q.get_nowait() is None:
                        break
                    dropped += 1
                except Exception:
                    break
            if dropped:
                print(f"[hermes] {dropped} Wiederholungs-Ereignisse verworfen", flush=True)
        else:
            res = await self.call("session/new", {"cwd": self.cwd, "mcpServers": []},
                                  timeout=180)
            self.session_id = (res or {}).get("sessionId") or ""
        if not self.session_id:
            raise AcpError("Hermes hat keine Sitzung geöffnet."
                           + ("\n" + self.stderr_text() if self.stderr_text() else ""))
        emit({"type": "session", "session_id": "hermes-" + self.session_id})

        if self.model:
            # Fehlschlag ist kein Abbruch: dann läuft das voreingestellte Modell.
            # Eine Antwort vom falschen Modell ist besser als gar keine — aber
            # stillschweigend wäre es eine Falle, deshalb steht es dann im Chat.
            try:
                await self.call("session/set_model",
                                {"sessionId": self.session_id,
                                 "modelId": acp_model_id(self.model)},
                                timeout=60)
            except Exception as e:
                emit({"type": "text", "text":
                      f"_⚠ Modell „{self.model}“ ließ sich nicht einstellen ({e}) — "
                      "es antwortet das in Hermes voreingestellte Modell._\n\n"})

        self._next_id += 1
        prompt_id = self._next_id
        prompt_fut = asyncio.get_running_loop().create_future()
        self._pending[prompt_id] = prompt_fut
        blocks = _image_blocks(images) + [{"type": "text", "text": prompt}]
        self._send({"jsonrpc": "2.0", "id": prompt_id, "method": "session/prompt",
                    "params": {"sessionId": self.session_id, "prompt": blocks}})
        await self.proc.stdin.drain()

        state = {"thinking_sent": False}
        last_event = time.monotonic()
        while not prompt_fut.done():
            get = asyncio.ensure_future(self._q.get())
            done, _ = await asyncio.wait({get, prompt_fut}, timeout=60,
                                         return_when=asyncio.FIRST_COMPLETED)
            if not done:
                # Stille. Solange ein Werkzeug offen ist, ist das normal (langer
                # Build); OHNE offenes Werkzeug heißt lange Stille, dass der
                # Modell-Stream hängt — dann abbrechen statt ewig warten.
                get.cancel()
                if not self._open_tools and time.monotonic() - last_event > IDLE_TIMEOUT:
                    self.kill()
                    raise AcpError(
                        f"Keine Reaktion seit {int(IDLE_TIMEOUT // 60)} Minuten — "
                        "Lauf abgebrochen (Modell/Anbieter hängt?)."
                        + ("\n" + self.stderr_text() if self.stderr_text() else ""))
                continue
            if get not in done:
                get.cancel()
                break
            msg = get.result()
            if msg is None:            # stdout zu Ende
                break
            last_event = time.monotonic()
            await self._handle(msg, emit, state, allow_writes)

        # Nachzügler abarbeiten. Die Abschlussmeldung eines Werkzeugs kommt oft
        # unmittelbar vor der Prompt-Antwort — bricht man hier sofort ab, bleibt
        # die Werkzeug-Anzeige in der Oberfläche für immer auf "läuft".
        while True:
            try:
                msg = self._q.get_nowait()
            except Exception:
                break
            if msg is None:
                break
            await self._handle(msg, emit, state, allow_writes)

        try:
            result = await prompt_fut      # wirft, wenn Hermes einen Fehler meldete
        except AcpError as e:
            # Auch im Fehlerfall darf keine Werkzeug-Anzeige auf „läuft“
            # stehen bleiben.
            self._close_open_tools(emit, f"abgebrochen: {e}")
            raise
        # Offen gebliebene Werkzeuge schliessen. Hermes meldet den Abschluss
        # eines Werkzeugs erst im NAECHSTEN Agenten-Schritt — das letzte vor der
        # Antwort bekommt deshalb nie eine Abschlussmeldung. Ohne das hier bliebe
        # dessen Anzeige fuer immer auf "laeuft". Der Lauf ist an dieser Stelle
        # sauber beendet, das Werkzeug also gelaufen; nur seine Ausgabe kennen
        # wir nicht — und genau das steht dann auch da.
        self._close_open_tools(emit, "")
        return result

    async def _handle(self, msg: dict, emit, state: dict, allow_writes: bool):
        """Eine eingehende Mitteilung oder Anfrage verarbeiten."""
        method = msg.get("method")

        # Anfrage DES AGENTEN — muss beantwortet werden, sonst wartet er ewig
        if "id" in msg and method:
            if method == "session/request_permission":
                self.reply(msg["id"], {"outcome": {
                    "outcome": "selected",
                    "optionId": _permission_choice(msg.get("params") or {}, allow_writes),
                }})
            else:
                # Unbekanntes höflich ablehnen statt schweigen: Schweigen liesse
                # den Agenten bis zum Zeitüberlauf warten.
                self._send({"jsonrpc": "2.0", "id": msg["id"],
                            "error": {"code": -32601, "message": "not supported"}})
            await self.proc.stdin.drain()
            return

        if method != "session/update":
            return
        u = ((msg.get("params") or {}).get("update")) or {}
        kind = u.get("sessionUpdate")

        if kind == "agent_message_chunk":
            txt = ((u.get("content") or {}).get("text")) or ""
            if txt:
                emit({"type": "text", "text": friendly_failure(txt) or txt})
        elif kind == "agent_thought_chunk":
            if not state["thinking_sent"]:
                state["thinking_sent"] = True
                emit({"type": "thinking_marker"})
        elif kind == "tool_call":
            tid = u.get("toolCallId")
            if tid and tid not in self._open_tools:
                self._open_tools.append(tid)
            emit({"type": "tool", "id": tid,
                  "name": u.get("title") or u.get("kind") or "Werkzeug",
                  "input": _tool_input(u)})
        elif kind in ("tool_call_update", "tool_call_progress"):
            if u.get("status") in ("completed", "failed"):
                tid = u.get("toolCallId")
                if tid in self._open_tools:
                    self._open_tools.remove(tid)
                emit({"type": "tool_result", "id": tid,
                      "content": _tool_output(u)[:6000],
                      "is_error": u.get("status") == "failed"})

    def _close_open_tools(self, emit, note: str):
        for tid in list(self._open_tools):
            emit({"type": "tool_result", "id": tid,
                  "content": note or "(fertig — Hermes meldet zum letzten "
                                     "Werkzeug eines Laufs keine Ausgabe)",
                  "is_error": bool(note)})
        self._open_tools.clear()

    def cancel(self):
        """Stop-Knopf: erst höflich abbrechen; das Töten macht der Aufrufer."""
        try:
            if self.proc and self.session_id and self.proc.returncode is None:
                self.notify("session/cancel", {"sessionId": self.session_id})
        except Exception:
            pass

    def kill(self):
        try:
            if self.proc and self.proc.returncode is None:
                self.proc.kill()
        except Exception:
            pass


# Bilder in ACP-Blöcke. Der Server hat sie beim Upload schon geprüft und in
# uploads/ abgelegt; hier werden sie nur eingebettet.
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
MAX_IMAGE = 8 * 1024 * 1024      # base64 bläht um ~4/3; darüber wird der Prompt untragbar


def _image_blocks(paths) -> list:
    import base64
    out = []
    for p in (paths or []):
        try:
            f = Path(p)
            mime = _MIME.get(f.suffix.lower())
            if not mime or not f.is_file() or f.stat().st_size > MAX_IMAGE:
                continue
            out.append({"type": "image", "mimeType": mime,
                        "data": base64.b64encode(f.read_bytes()).decode("ascii")})
        except Exception:
            continue
    return out


def _history_fallback(sid: str) -> str:
    """Verlauf einer nicht mehr ladbaren Sitzung als Textblock.

    Gleiche Konvention wie carry_over_block in server/hermes_runs.py: keine echte Fortsetzung
    (Werkzeug-Zustand ist weg), aber ehrlicher als ein Assistent ohne Gedächtnis.
    """
    # config erst hier laden (wie in hermes_home): auf Modulebene gäbe es
    # einen Import-Kreis über llm. Der Import fehlte früher ganz — beim
    # Wiederaufnehmen einer kaputten Hermes-Sitzung wäre das ein NameError.
    from server import config as cfg
    msgs = session_messages(sid)
    if not msgs:
        return ""
    lines = [cfg.L("[Kontext: Die bisherige Sitzung ließ sich technisch nicht "
                   "fortsetzen; dies ist ihr Verlauf:]",
                   "[Context: the previous session could not be resumed for technical "
                   "reasons; this is its history:]")]
    total = 0
    for m in msgs[-30:]:
        t = str(m.get("text") or "")
        total += len(t)
        if total > 40000:
            break
        lines.append((cfg.L("Nutzer: ", "User: ") if m.get("role") == "user"
                      else cfg.L("Assistent: ", "Assistant: ")) + t)
    lines.append(cfg.L("[Ende des Verlaufs — antworte auf die folgende neue Nachricht.]",
                       "[End of history — reply to the following new message.]"))
    return "\n\n".join(lines)


def _permission_choice(params: dict, allow_writes: bool) -> str:
    """Welche der angebotenen Optionen der Agent bekommt.

    Der 🛡-Modus der Oberfläche entscheidet: im Plan-Modus wird alles
    Verändernde abgelehnt, sonst durchgewunken. Gesucht wird nach `kind`,
    nicht nach Beschriftung — die kann übersetzt sein.
    """
    opts = params.get("options") or []
    want = ("allow_always", "allow_once") if allow_writes else ("reject_once", "reject_always")
    for kind in want:
        for o in opts:
            if o.get("kind") == kind:
                return o.get("optionId") or ""
    return (opts[0].get("optionId") if opts else "") or ""


def _tool_input(u: dict) -> dict:
    """Was das Werkzeug bekommen hat — fürs Aufklappen in der Oberfläche."""
    raw = u.get("rawInput")
    if isinstance(raw, dict) and raw:
        return raw
    locs = [l.get("path") for l in (u.get("locations") or []) if l.get("path")]
    return {"file_path": locs[0]} if locs else {}


def _tool_output(u: dict) -> str:
    out = u.get("rawOutput")
    if isinstance(out, str) and out.strip():
        return out
    parts = []
    for c in (u.get("content") or []):
        if not isinstance(c, dict):
            continue
        inner = c.get("content") if isinstance(c.get("content"), dict) else c
        t = inner.get("text") if isinstance(inner, dict) else None
        if t:
            parts.append(str(t))
    if parts:
        return "\n".join(parts)
    return json.dumps(out, ensure_ascii=False)[:2000] if out is not None else ""


# ---------- Sitzungen (aus Hermes' Datenbank, lesend) ----------
# Über `session/list` ginge es auch, aber dafür müsste für jede Anzeige ein
# hermes-Prozess starten — beim Aufbau der Seitenleiste wären das Sekunden.
# Die Datenbank liegt lokal und wird nur lesend geöffnet.
def _db_path() -> Path:
    return Path(hermes_home()) / "state.db"


def _db():
    import sqlite3
    return sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True, timeout=3)


def list_sessions() -> list:
    """Hermes-Sitzungen im Format der Session-Liste (app.py mischt sie dazu)."""
    if not _db_path().exists():
        return []
    out = []
    try:
        con = _db()
        rows = con.execute(
            "SELECT id, title, cwd, model, last_activity_at, started_at, "
            "message_count, model_config "
            "FROM sessions WHERE source='acp' AND COALESCE(hidden,0)=0 "
            "ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT 300").fetchall()
        con.close()
    except Exception:
        return []
    for sid, title, cwd, model, last, started, cnt, mcfg in rows:
        if not cwd:
            # Die eigene Spalte bleibt bei ACP-Sitzungen leer; der Ordner steht
            # in der Konfiguration, die beim Sitzungsstart mitgeschrieben wird.
            try:
                cwd = (json.loads(mcfg or "{}") or {}).get("cwd") or ""
            except Exception:
                cwd = ""
        out.append({
            "id": "hermes-" + sid,
            "project": "hermes",
            "cwd": cwd or "(unbekannt)",
            "title": (title or "").strip() or "(ohne Titel)",
            "mtime": float(last or started or 0),
            "size": int(cnt or 0),
            "model": model or "",
        })
    return out


_SID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{5,63}$")


def delete_session(sid: str) -> bool:
    """Sitzung samt Nachrichten löschen — über das CLI, das die DB-Details kennt
    (direkt in state.db zu schreiben hieße, Hermes' Schema nachzubauen)."""
    if not hermes_bin() or not _SID_OK.match(sid or ""):
        return False
    try:
        import subprocess
        r = subprocess.run([hermes_bin(), "sessions", "delete", "--yes", sid],
                           capture_output=True, text=True, timeout=30, env=child_env())
        return r.returncode == 0 and "delete" in (r.stdout or "").lower()
    except Exception:
        return False


def session_messages(sid: str) -> list:
    """Verlauf einer Sitzung im Anzeige-Format der Verlaufs-Ansicht."""
    if not _db_path().exists():
        return []
    try:
        con = _db()
        rows = con.execute(
            "SELECT role, content, tool_calls, tool_name FROM messages "
            "WHERE session_id=? AND COALESCE(active,1)=1 ORDER BY CAST(id AS INTEGER)",
            (sid,)).fetchall()
        con.close()
    except Exception:
        return []
    msgs = []
    for role, content, tool_calls, tool_name in rows:
        text = (content or "").strip()
        if role == "user":
            text = strip_context(text)
        elif role == "assistant":
            text = friendly_failure(text) or text
        if role == "tool":
            # Werkzeug-Ausgaben gehören nicht in den Gesprächsverlauf: sie sind
            # oft seitenlang und stehen im Chat ohnehin in eigenen Kästen.
            continue
        if role == "assistant" and not text and tool_calls:
            names = []
            try:
                names = [c.get("function", {}).get("name") or c.get("name")
                         for c in json.loads(tool_calls)]
            except Exception:
                pass
            names = [n for n in names if n]
            text = "🔧 " + ", ".join(names) if names else "🔧 Werkzeug"
        if not text:
            continue
        msgs.append({"role": "user" if role == "user" else "assistant", "text": text})
    return msgs
