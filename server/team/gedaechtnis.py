"""Das Gedächtnis der Mitarbeiter: Direktgespräch, Verdichten, Eindicken.

Ein Mitarbeiter hat zwei Arten, sich etwas zu merken (siehe agents.py,
anleitungen.py), und ein Gespräch mit dem Nutzer, das nicht ewig wachsen darf.
Die langlebige Sitzung im Direktgespräch wird ab einer Größe verdichtet: das
Bleibende wandert ins MEMORY.md, der Verlauf wird geschlossen.
"""
import asyncio
import json
import time
from pathlib import Path

from server.core import PROJECTS_DIR
from server.sessions import SID_RE, _parse_transcript_lines
from server.team import agents as ag
from server.team.lauf import build_claude_cmd, spawn


def chat_state_file(slug: str) -> Path:
    return ag.AGENTS_DIR / slug / "chat.json"


def chat_session_id(slug: str) -> str:
    """Die Sitzung des Direktgespraechs — aber nur, wenn es sie wirklich gibt.

    Zeigt der Zeiger ins Leere (Transkript von Hand geloescht, Projektordner
    umgezogen, `claude` aufgeraeumt), scheitert sonst JEDER weitere Zug mit
    "--resume: no conversation found" — und in der Oberflaeche sieht das aus,
    als sei der Mitarbeiter kaputt. Lieber ein frisches Gespraech: das
    Gedaechtnis (MEMORY.md) haengt ohnehin am Systemprompt, verloren geht also
    nur der Wortlaut, den es schon nicht mehr gibt.
    """
    try:
        sid = json.loads(chat_state_file(slug).read_text(encoding="utf-8")).get("session_id") or ""
    except Exception:
        return ""
    if not sid or not SID_RE.match(sid):
        return ""
    if next(iter(PROJECTS_DIR.glob(f"*/{sid}.jsonl")), None) is None:
        print(f"[chat] {slug}: Transkript zu {sid[:8]} fehlt — fange frisch an", flush=True)
        try:
            chat_state_file(slug).unlink()
        except OSError:
            pass
        return ""
    return sid


def set_chat_session(slug: str, sid: str):
    ag._atomic(chat_state_file(slug),
               json.dumps({"session_id": sid, "ts": time.time()}, ensure_ascii=False))


# Im Direktgespraech gibt es nur diese — kein Delegieren, kein Liefern.
CHAT_WERKZEUGE = ("merken", "user_merken", "belegschaft", "auftrag_anlegen",
                  "rechnen", "kontrast", "anleitung", "anleitung_anlegen")


# ---------- Verdichten: damit ein Gespräch nicht ewig wächst ----------
# Eine langlebige Sitzung ist im Direktgespräch richtig (eine Beziehung, kein
# abgegrenzter Vorgang) — aber sie waechst mit jeder Nachricht, und irgendwann
# zahlt jeder Zug den ganzen bisherigen Verlauf mit.
#
# Statt das autocompact von Claude Code machen zu lassen (das den Kontext
# zusammenfasst und danach VERGISST), machen wir es selbst und heben das
# Wesentliche ins MEMORY.md: dort ueberlebt es die Sitzung und steht beim
# naechsten Mal wieder im Systemprompt. Genau das meint "der Agent lernt".
# Kennzeile fuer Laeufe, die die Firma fuer sich selbst startet (Verdichten,
# Gedaechtnis eindicken) — nicht fuer Arbeit an einem Auftrag.
#
# Warum sie noetig ist: Claude Code legt fuer jeden Lauf eine Sitzung unter
# ~/.claude/projects/<ordner>/ ab, und die Sitzungsliste zeigt genau die. Zuege in
# Auftraegen erkennt sie an den `mcp__firma__`-Werkzeugen in der Werkzeugliste;
# diese internen Laeufe haben aber gar keinen Bus und saehen dort aus wie ein
# Gespraech des Nutzers. Die Zeile steht am Anfang des Prompts, also im
# Transkript (INTERN_MARKEN in server/sessions.py) — sie ist absichtlich
# haesslich, damit sie nie zufaellig entsteht.
INTERN_MARKE = "[firma-intern]"

CHAT_MAX_BYTES = 220_000     # Transkriptgroesse, ab der verdichtet wird
CHAT_MAX_MSGS = 40


def chat_umfang(slug: str) -> tuple:
    sid = chat_session_id(slug)
    if not sid or not SID_RE.match(sid):
        return 0, 0
    f = next(iter(PROJECTS_DIR.glob(f"*/{sid}.jsonl")), None)
    if f is None:
        return 0, 0
    try:
        roh = f.read_bytes()
    except OSError:
        return 0, 0
    return len(roh), len(_parse_transcript_lines(roh))


async def verdichten(a: dict) -> bool:
    """Gespräch zusammenfassen, Erkenntnisse ins MEMORY.md, Sitzung schliessen.

    Laeuft als eigener, kurzer Lauf ohne Werkzeuge — er soll nur lesen und
    schreiben, nicht arbeiten.
    """
    slug = a["slug"]
    groesse, anzahl = chat_umfang(slug)
    if groesse < CHAT_MAX_BYTES and anzahl < CHAT_MAX_MSGS:
        return False
    sid = chat_session_id(slug)
    alt = ag._read_capped(ag.AGENTS_DIR / slug / "MEMORY.md", ag.MAX_MEMORY)
    auftrag = (
        f"{INTERN_MARKE}\n"
        "Das Gespräch mit Kevin ist lang geworden und wird gleich neu begonnen. "
        "Fasse zusammen, was du behalten musst — nicht den Verlauf, sondern das "
        "BLEIBENDE: Entscheidungen, Vorlieben, offene Punkte, was du fachlich "
        "gelernt hast.\n\n"
        "Antworte NUR mit dem neuen Inhalt deiner MEMORY.md, als Stichpunktliste, "
        "höchstens 40 Zeilen. Keine Einleitung, keine Anrede. Was schon dasteht, "
        "übernimmst du (gekürzt, wenn es sich überschneidet).\n\n"
        f"Bisher steht dort:\n{alt or '(noch nichts)'}")
    cmd = build_claude_cmd(mode="plan", model=a["model"], effort="low",
                           session_id=sid or None, intern=True)
    run = spawn(cmd, a["cwd"], a["model"], auftrag, sid or None, agent_slug=slug)

    def _zurueck():
        # Verdichten ist Kuer: klappt es nicht, laeuft das Gespraech weiter wie
        # bisher — aber mit der ALTEN Sitzung. Der Verdichten-Lauf hat sie
        # per set_chat_session schon auf seine eigene umgebogen.
        if sid:
            set_chat_session(slug, sid)
        return False

    try:
        await asyncio.wait_for(run.task, timeout=180)
    except asyncio.TimeoutError:
        run.task.cancel()
        print(f"[verdichten] {slug}: Zeitlimit", flush=True)
        return _zurueck()
    text = (run.last_text or "").strip()
    if len(text) < 20:
        return _zurueck()
    ag._atomic(ag.AGENTS_DIR / slug / "MEMORY.md", text[:ag.MAX_MEMORY])
    # Sitzung schliessen: der naechste Zug faengt frisch an — mit dem
    # verdichteten Gedaechtnis im Systemprompt.
    try:
        chat_state_file(slug).unlink()
    except OSError:
        pass
    return True


MEM_LOCKS = {}


def mem_lock(slug: str) -> asyncio.Lock:
    """Ein Schloss pro Personalakte.

    `merken` und das Eindicken lesen MEMORY.md, rechnen und schreiben es
    zurueck. Ohne Schloss verliert der eine den Eintrag des anderen, sobald
    derselbe Mitarbeiter in zwei Auftraegen gleichzeitig arbeitet — `_atomic`
    schuetzt die Datei, nicht die Lese-Schreib-Folge.
    """
    lock = MEM_LOCKS.get(slug)
    if lock is None:
        lock = MEM_LOCKS[slug] = asyncio.Lock()
    return lock


async def gedaechtnis_eindicken(a: dict) -> bool:
    """Das MEMORY.md eines Mitarbeiters kuerzen — unabhaengig vom Direktchat.

    Warum das eigens noetig ist: `verdichten()` haengt am Direktgespraech und
    laeuft nur an, wenn dessen Transkript ueber CHAT_MAX_BYTES waechst. Gefuellt
    wird das Gedaechtnis aber in der AUFTRAGSARBEIT. Wer viel arbeitet und
    selten mit Kevin redet — Selma etwa, 5268 von 8000 Zeichen ohne ein
    einziges langes Gespraech — lief so auf die Grenze zu und konnte danach
    DAUERHAFT nichts mehr lernen: `merken` scheiterte jedes Mal und verwies auf
    eine Verdichtung, die nie kam. Aufgefallen waere das niemandem, die
    Fehlermeldung geht an den Agenten, nicht an Kevin.

    Bewusst OHNE agent_slug gespawnt: ein Lauf mit Slug und ohne Ticket biegt
    per set_chat_session die Direktchat-Sitzung des Mitarbeiters auf sich um
    (siehe run_claude) — Kevins naechstes Gespraech landete dann mitten im
    Eindicken. `verdichten()` repariert das hinterher, hier entsteht es nicht.
    """
    slug = a["slug"]
    p = ag.AGENTS_DIR / slug / "MEMORY.md"
    alt = ag._read_capped(p, 10 ** 9)
    if len(alt) < 200:
        return False
    ziel = int(ag.MAX_MEMORY * 0.55)
    auftrag = (
        f"{INTERN_MARKE}\n"
        "Das unten ist dein Gedaechtnis. Es ist an die Grenze gestossen und "
        f"muss eingedickt werden — auf hoechstens {ziel} Zeichen.\n\n"
        "Behalte, was dir bei der Arbeit noch nuetzt: gemessene Werte, "
        "Entscheidungen, Fallen, auf die du schon einmal getreten bist. Wirf "
        "weg, was erledigt oder veraltet ist oder nur einmal gebraucht wurde. "
        "Fasse zusammen, was sich ueberschneidet.\n\n"
        "Erfinde nichts dazu, und mach aus keiner konkreten Zahl eine "
        "Faustregel — genau die Zahlen sind der Grund, warum du dir das "
        "aufgeschrieben hast.\n\n"
        "Antworte NUR mit dem neuen Inhalt, als Stichpunktliste. Keine "
        f"Einleitung, keine Anrede.\n\nDein Gedaechtnis:\n{alt}")
    cmd = build_claude_cmd(mode="plan", model=a["model"], effort="low", intern=True)
    run = spawn(cmd, a["cwd"], a["model"], auftrag)
    try:
        await asyncio.wait_for(run.task, timeout=180)
    except asyncio.TimeoutError:
        run.task.cancel()
        print(f"[gedaechtnis] {slug}: Zeitlimit beim Eindicken", flush=True)
        return False
    neu = (run.last_text or "").strip()
    # Nur uebernehmen, wenn wirklich etwas Kuerzeres und Substanzielles kam.
    # Ein leerer, abgebrochener oder schwatzhafter Lauf darf ein gefuelltes
    # Gedaechtnis nicht leeren — im Zweifel bleibt das alte stehen.
    if len(neu) < 100 or len(neu) >= len(alt):
        print(f"[gedaechtnis] {slug}: Eindicken verworfen "
              f"({len(alt)} -> {len(neu)} Zeichen)", flush=True)
        return False
    ag._atomic(p, neu[:ag.MAX_MEMORY].rstrip("\n") + "\n")
    print(f"[gedaechtnis] {slug}: eingedickt, {len(alt)} -> {len(neu)} Zeichen",
          flush=True)
    return True
