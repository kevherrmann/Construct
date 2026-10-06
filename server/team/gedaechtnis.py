"""Das Gedächtnis der Mitarbeiter: Eindicken, wenn es voll ist.

Ein Mitarbeiter hat zwei Arten, sich etwas zu merken (siehe agents.py,
anleitungen.py). Das MEMORY.md wächst bei der Arbeit an Aufträgen; stößt es an
seine Grenze, wird es eingedickt: das Bleibende bleibt, Erledigtes fliegt raus.
"""
import asyncio

from server.team import agents as ag
from server.team.lauf import build_claude_cmd, spawn


# Kennzeile fuer Laeufe, die die Firma fuer sich selbst startet (Gedaechtnis
# eindicken) — nicht fuer Arbeit an einem Auftrag.
#
# Warum sie noetig ist: Claude Code legt fuer jeden Lauf eine Sitzung unter
# ~/.claude/projects/<ordner>/ ab, und die Sitzungsliste zeigt genau die. Zuege in
# Auftraegen erkennt sie an den `mcp__firma__`-Werkzeugen in der Werkzeugliste;
# diese internen Laeufe haben aber gar keinen Bus und saehen dort aus wie ein
# Gespraech des Nutzers. Die Zeile steht am Anfang des Prompts, also im
# Transkript (INTERN_MARKEN in server/sessions.py) — sie ist absichtlich
# haesslich, damit sie nie zufaellig entsteht.
INTERN_MARKE = "[firma-intern]"


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
    """Das MEMORY.md eines Mitarbeiters kuerzen.

    Gefuellt wird das Gedaechtnis in der AUFTRAGSARBEIT. Ohne Eindicken lief
    ein Mitarbeiter, der viel arbeitet (Elara etwa, 5268 von 8000 Zeichen), auf
    die Grenze zu und konnte danach DAUERHAFT nichts mehr lernen: `merken`
    scheiterte jedes Mal. Aufgefallen waere das niemandem, die Fehlermeldung
    geht an den Agenten, nicht an Kevin.
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
