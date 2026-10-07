"""Tickets — das Board.

Fünf Spalten: Neu, In Arbeit, In Review, QA, Done. Ein Board für Menschen wie
für die Firma, darum lässt sich jede Karte von Hand ziehen.

Woher Tickets kommen:

  1. Von Hand am Board, in Neu. Der Assistent fasst sie nur an, wenn der Nutzer
     es sagt („mach T-12“) — dann über das CLI tickets.py.
  2. Aus Commits. Jeder Lauf liest mit, ob `git commit` lief (git schreibt
     `[main abc1234] Betreff`). Alle Commits eines Laufs werden EIN Ticket —
     sonst gäbe jedes „Frontend neu gebaut“ eine eigene Karte. Nennt die
     Commit-Nachricht ein Ticket (`T-12`), hängt der Commit dort an.
  3. Aus einem Auftrag der Firma, in In Arbeit.

Früher war ein Ticket ein Abschnitt einer Session, den der Assistent mit
Markerzeilen pflegte. Das musste raten, was eine Aufgabe ist und wann sie
anfängt. Ein Commit sagt beides von selbst.

Wie Karten wandern:

  - Commit ohne Firma → QA. In einem Auftrag bleibt die Karte, wo die Firma sie
    hat; wer eine Spalte in seiner Akte trägt (Janus: review, Miranda: qa),
    zieht sie dorthin, sobald er drankommt. Ein fertiger Auftrag → QA.
  - Sind alle Commits einer Karte auf dem Remote → Done (der Server fragt git).
  - Von Hand: immer. Wer eine Karte nach dem letzten Commit selbst gezogen hat,
    dem schiebt die Push-Prüfung sie nicht wieder weg.

Ablage: tickets/board.json, eine Datei. Keine Datenbank: eine verrutschte
Karte muss sich im Editor geradeziehen lassen. Steht in .gitignore.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from server import config as cfg
from server.core import BASE_DIR

TICKETS_DIR = BASE_DIR / "tickets"
BOARD = TICKETS_DIR / "board.json"

SPALTEN = ("neu", "arbeit", "review", "qa", "done")
TITEL_MAX = 80
TEXT_MAX = 20000
# Ein Commit-Betreff wird zum Titel. Länger liest sich auf einer Karte nicht.
TITEL_KURZ = 60
GIT_TIMEOUT = 10

# T-12 in einer Commit-Nachricht. Nicht #12: auf GitHub verlinkt das auf ein
# fremdes Issue gleicher Nummer.
VERWEIS_RE = re.compile(r"\bT-(\d{1,6})\b")


# ---------- Datei ----------
_LOCK = threading.Lock()


@contextmanager
def _sperre():
    """Server und CLI schreiben dieselbe Datei: ein Schloss im Prozess, dazu
    eine Dateisperre über Prozesse hinweg (wo es fcntl gibt)."""
    with _LOCK:
        TICKETS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            import fcntl
        except ImportError:                    # Windows: nur das Schloss im Prozess
            yield
            return
        with open(TICKETS_DIR / ".lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _leer() -> dict:
    return {"zaehler": 0, "tickets": []}


def _commit_bereinigt(c) -> dict | None:
    if not isinstance(c, dict) or not re.fullmatch(r"[0-9a-f]{7,40}", str(c.get("sha") or "")):
        return None
    return {"sha": c["sha"], "repo": str(c.get("repo") or ""), "branch": str(c.get("branch") or ""),
            "betreff": str(c.get("betreff") or "")[:200], "ts": str(c.get("ts") or ""),
            "von": str(c.get("von") or ""), "gepusht": bool(c.get("gepusht"))}


def _bereinigt(d: dict) -> dict:
    """Gelesene Datei auf Form bringen. Von Hand bearbeitet darf sie unvollständig
    sein; ein Tippfehler macht eine Karte kaputt, nicht das Board."""
    out = _leer()
    try:
        out["zaehler"] = max(0, int(d.get("zaehler") or 0))
    except (TypeError, ValueError):
        pass
    for t in d.get("tickets") if isinstance(d.get("tickets"), list) else []:
        if not isinstance(t, dict):
            continue
        try:
            nr = int(t.get("nr"))
        except (TypeError, ValueError):
            continue
        if nr < 1 or any(x["nr"] == nr for x in out["tickets"]):
            continue
        out["tickets"].append({
            "nr": nr,
            "titel": str(t.get("titel") or f"Ticket {nr}")[:TITEL_MAX],
            "text": str(t.get("text") or "")[:TEXT_MAX],
            "spalte": t.get("spalte") if t.get("spalte") in SPALTEN else "neu",
            "projekt": str(t.get("projekt") or ""),
            "von": str(t.get("von") or ""),
            "erstellt": str(t.get("erstellt") or ""),
            "geaendert": str(t.get("geaendert") or t.get("erstellt") or ""),
            # Wann zuletzt jemand von Hand gezogen hat — dagegen kommt die
            # Push-Prüfung nicht an.
            "hand": str(t.get("hand") or ""),
            "session": str(t.get("session") or ""),
            "uuid": str(t.get("uuid") or ""),
            "auftrag": str(t.get("auftrag") or "") or None,
            "commits": [c for c in map(_commit_bereinigt, t.get("commits") or []) if c],
        })
    out["zaehler"] = max([out["zaehler"], *(t["nr"] for t in out["tickets"])])
    return out


def laden() -> dict:
    try:
        d = json.loads(BOARD.read_text(encoding="utf-8"))
    except OSError:
        return _leer()
    except ValueError:
        # Von Hand kaputtgespeichert: NICHT stillschweigend durch ein leeres
        # Board ersetzen, das der nächste Speichervorgang darüber schriebe.
        sicher = BOARD.with_name(BOARD.name + ".kaputt")
        try:
            if not sicher.exists():
                shutil.copy2(BOARD, sicher)
        except OSError:
            pass
        return _leer()
    return _bereinigt(d if isinstance(d, dict) else {})


def speichern(d: dict):
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BOARD.with_name(f"{BOARD.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(BOARD)


@contextmanager
def _aendern():
    """Lesen, ändern, schreiben — unter einer Sperre."""
    with _sperre():
        d = laden()
        yield d
        speichern(d)


def _ticket(d: dict, nr) -> dict | None:
    try:
        nr = int(nr)
    except (TypeError, ValueError):
        return None
    return next((t for t in d["tickets"] if t["nr"] == nr), None)


def _neu(d: dict, titel: str, spalte: str = "neu", **felder) -> dict:
    """Nummern werden nie wiederverwendet: eine Commit-Nachricht verweist mit
    T-12 dauerhaft auf genau diese Karte."""
    d["zaehler"] = max(d["zaehler"], *(t["nr"] for t in d["tickets"]), 0) + 1
    jetzt = _jetzt()
    t = {"nr": d["zaehler"], "titel": (titel or "").strip()[:TITEL_MAX] or cfg.L("Ohne Titel", "Untitled"),
         "text": "", "spalte": spalte, "projekt": "", "von": "", "erstellt": jetzt,
         "geaendert": jetzt, "hand": "", "session": "", "uuid": "", "auftrag": None, "commits": []}
    t.update({k: v for k, v in felder.items() if k in t})
    d["tickets"].append(t)
    return t


def _schieben(t: dict, spalte: str):
    if spalte in SPALTEN and t["spalte"] != spalte:
        t["spalte"] = spalte
        t["geaendert"] = _jetzt()


# ---------- Am Board (Nutzer, Oberfläche, CLI) ----------
def anlegen(titel: str, text: str = "", projekt: str = "", spalte: str = "neu", von: str = "kevin") -> dict:
    titel = (titel or "").strip()
    if not titel:
        raise ValueError(cfg.L("Titel fehlt", "title missing"))
    with _aendern() as d:
        return _neu(d, titel, spalte if spalte in SPALTEN else "neu",
                    text=str(text or "")[:TEXT_MAX], projekt=str(projekt or ""), von=von)


def aendern(nr: int, titel=None, text=None, spalte=None, projekt=None) -> dict:
    with _aendern() as d:
        t = _ticket(d, nr)
        if t is None:
            raise KeyError(nr)
        if titel is not None and str(titel).strip():
            t["titel"] = str(titel).strip()[:TITEL_MAX]
        if text is not None:
            t["text"] = str(text)[:TEXT_MAX]
        if projekt is not None:
            t["projekt"] = str(projekt)
        if spalte is not None:
            if spalte not in SPALTEN:
                raise ValueError(cfg.L("unbekannte Spalte", "unknown column"))
            _schieben(t, spalte)
            t["hand"] = _jetzt()
        t["geaendert"] = _jetzt()
        return t


def loeschen(nr: int):
    with _aendern() as d:
        t = _ticket(d, nr)
        if t is None:
            raise KeyError(nr)
        d["tickets"].remove(t)


def holen(nr: int) -> dict | None:
    return _ticket(laden(), nr)


# ---------- Aus Commits ----------
# `[main abc1234] Betreff`, `[main (root-commit) abc1234] …`, `[detached HEAD abc1234] …`.
# Die Klammer ist übersetzt (deutsches git: „(Root-Commit)“), darum jede.
COMMIT_RE = re.compile(r"^\[(?P<branch>[^\]\n(]+?) (?:\([^)\n]*\) )?(?P<sha>[0-9a-f]{7,40})\] (?P<betreff>.*)$",
                       re.M)
# Wo ein Befehl hingeht: `cd ordner && git commit …`, `git -C ordner commit …`
_ORT_RE = re.compile(r"""(?:\bcd|\bgit\s+-C)\s+("[^"]+"|'[^']+'|[^\s;&|]+)""")


def ist_commit_befehl(befehl: str) -> bool:
    return "git" in befehl and "commit" in befehl


def _git(repo: str, *args) -> str | None:
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                           timeout=GIT_TIMEOUT, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _repos(befehl: str, cwd: str) -> list[str]:
    """Repo-Wurzeln, in denen der Befehl gewirkt haben kann: die Ordner, die er
    nennt, dann der Arbeitsordner des Laufs."""
    orte = []
    basis = Path(cwd or ".")
    for m in _ORT_RE.finditer(befehl or ""):
        p = Path(os.path.expanduser(m.group(1).strip("\"'")))
        orte.append(p if p.is_absolute() else basis / p)
    orte.append(basis)
    out = []
    for ort in orte:
        top = (_git(str(ort), "rev-parse", "--show-toplevel") or "").strip()
        if top and top not in out:
            out.append(top)
    return out


def _gefundene(ausgabe: str, befehl: str, cwd: str, seit: float | None) -> list[tuple[str, str, str]]:
    """(Repo, voller Hash, Branch) der Commits dieses Befehls.

    Erst aus der Ausgabe (`[main abc1234] …`). Mit `git commit -q` schreibt git die
    Zeile aber nicht (so committete Luna im ersten echten Durchlauf, 07.10.2026) —
    dann zählen die Commits, die seit dem Start des Befehls auf HEAD entstanden sind."""
    repos = _repos(befehl, cwd)
    out = []
    for c in commits_aus(ausgabe):
        for repo in repos:
            voll = (_git(repo, "rev-parse", "--verify", "--quiet", f"{c['sha']}^{{commit}}") or "").strip()
            if voll:
                out.append((repo, voll, c["branch"].strip()))
                break
    if out or seit is None:
        return out
    for repo in repos:
        # Commit-Zeit hat Sekunden: eine Sekunde Spielraum nach vorn.
        neu = _git(repo, "log", "--reverse", "--format=%H", f"--since=@{int(seit) - 1}", "HEAD")
        branch = (_git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
        out += [(repo, h, branch) for h in (neu or "").split()]
    return out


def kurz(betreff: str) -> str:
    """Titel aus einem Commit-Betreff: auf ein Wortende gekürzt."""
    s = " ".join((betreff or "").split())
    if len(s) <= TITEL_KURZ:
        return s
    cut = s[:TITEL_KURZ].rsplit(" ", 1)[0]
    return (cut if len(cut) > TITEL_KURZ // 2 else s[:TITEL_KURZ]).rstrip(" ,;:–-") + " …"


def commits_aus(ausgabe: str) -> list[dict]:
    return [m.groupdict() for m in COMMIT_RE.finditer(ausgabe or "")]


def commit_buchen(ausgabe: str, befehl: str, cwd: str, *, session: str = "", uuid: str = "",
                  von: str = "", auftrag: str = "", ticket: int | None = None,
                  seit: float | None = None) -> int | None:
    """Ein Lauf hat committet: den Commit an ein Ticket hängen. `seit` ist der
    Start des Befehls (Unix-Zeit), für Commits ohne Zeile in der Ausgabe.

    Ziel, in dieser Reihenfolge: das Ticket, das die Commit-Nachricht nennt (T-12);
    das Ticket des Auftrags; `ticket` (das dieser Lauf schon angelegt hat); sonst
    ein neues. Gibt die Nummer zurück, damit der Lauf weitere Commits dazulegt.
    """
    for repo, voll, branch in _gefundene(ausgabe, befehl, cwd, seit):
        nachricht = _git(repo, "log", "-1", "--format=%B", voll) or ""
        betreff, _, rumpf = nachricht.strip().partition("\n")
        eintrag = {"sha": voll, "repo": repo, "branch": branch,
                   "betreff": betreff.strip()[:200], "ts": _jetzt(), "von": von, "gepusht": False}
        with _aendern() as d:
            schon = next((x for x in d["tickets"] if any(c["sha"] == voll for c in x["commits"])), None)
            if schon:
                # Derselbe Commit noch einmal (ein Lauf, der nach einem Neustart
                # des Servers nachgelesen wird): nichts doppelt.
                ticket = schon["nr"]
                continue
            t = None
            m = VERWEIS_RE.search(nachricht)
            if m:
                t = _ticket(d, m.group(1))
            if t is None and auftrag:
                t = next((x for x in d["tickets"] if x["auftrag"] == auftrag), None)
            if t is None and ticket:
                t = _ticket(d, ticket)
            if t is None:
                t = _neu(d, kurz(betreff), "qa", text=rumpf.strip()[:TEXT_MAX], projekt=repo,
                         von=von or "assistent", session=session, uuid=uuid)
            if "--amend" in (befehl or ""):
                # Der vorige Commit ist ersetzt, nicht ergänzt.
                alt = [x for x in t["commits"] if x["repo"] == repo and x["branch"] == eintrag["branch"]]
                if alt:
                    t["commits"].remove(alt[-1])
            if not any(x["sha"] == voll for x in t["commits"]):
                t["commits"].append(eintrag)
            if not t["projekt"]:
                t["projekt"] = repo
            if not t["session"] and session:
                t["session"], t["uuid"] = session, uuid
            if t["auftrag"] and _auftrag_laeuft(t["auftrag"]):
                if t["spalte"] == "neu":
                    _schieben(t, "arbeit")
            else:
                _schieben(t, "qa")
            t["geaendert"] = _jetzt()
            ticket = t["nr"]
    return ticket


def _auftrag_laeuft(aid: str) -> bool:
    try:
        from server.team import auftraege as auf
        a = auf.laden(aid)
    except Exception:
        return False
    return bool(a) and a["status"] not in ("fertig", "abgebrochen")


# ---------- Push-Prüfung ----------
_PUSH = {"zuletzt": 0.0}
PUSH_TAKT = 15


def _gepusht(c: dict) -> bool:
    """Liegt der Commit auf einem Remote-Branch? Ohne Remote: nie."""
    out = _git(c["repo"], "branch", "-r", "--contains", c["sha"])
    return bool(out and out.strip())


def push_pruefen(erzwingen: bool = False) -> bool:
    """Karten, deren Commits alle auf dem Remote liegen, nach Done. Höchstens alle
    PUSH_TAKT Sekunden — das Board fragt alle paar Sekunden. True, wenn sich etwas
    geändert hat."""
    if not erzwingen and time.monotonic() - _PUSH["zuletzt"] < PUSH_TAKT:
        return False
    _PUSH["zuletzt"] = time.monotonic()
    offen = [(t["nr"], c["sha"], c["repo"]) for t in laden()["tickets"]
             if t["spalte"] != "done" and t["commits"] for c in t["commits"] if not c["gepusht"]]
    if not offen:
        return False
    jetzt_gepusht = {sha for _nr, sha, repo in offen if _gepusht({"sha": sha, "repo": repo})}
    if not jetzt_gepusht:
        return False
    with _aendern() as d:
        for t in d["tickets"]:
            for c in t["commits"]:
                if c["sha"] in jetzt_gepusht:
                    c["gepusht"] = True
            letzter = max((c["ts"] for c in t["commits"]), default="")
            von_hand = t["hand"] and t["hand"] > letzter
            if (t["spalte"] != "done" and t["commits"] and not von_hand
                    and all(c["gepusht"] for c in t["commits"])):
                _schieben(t, "done")
    return True


# ---------- Firma ----------
def auftrag_angelegt(auftrag_id: str, titel: str, brief: str, cwd: str, session: str = "",
                     ticket: int | None = None) -> int:
    """Die Firma hat einen Auftrag: seine Karte kommt nach In Arbeit — die genannte
    (T-12) oder eine neue."""
    with _aendern() as d:
        t = _ticket(d, ticket) if ticket else None
        if t is None:
            top = (_git(cwd, "rev-parse", "--show-toplevel") or "").strip() if cwd else ""
            t = _neu(d, kurz(titel), "arbeit", text=str(brief or "")[:TEXT_MAX],
                     projekt=top or cwd, von="assistent", session=session)
        t["auftrag"] = auftrag_id
        _schieben(t, "arbeit")
        return t["nr"]


def auftrag_spalte(auftrag_id: str, spalte: str):
    """Ein Mitarbeiter ist am Zug, oder der Auftrag ist fertig: die Karte folgt."""
    if spalte not in SPALTEN:
        return
    with _aendern() as d:
        for t in d["tickets"]:
            if t["auftrag"] == auftrag_id and t["spalte"] != "done":
                _schieben(t, spalte)


# ---------- Für die Oberfläche ----------
def board(projekt: str = "") -> dict:
    d = laden()
    tickets = [t for t in d["tickets"] if not projekt or t["projekt"] == projekt]
    projekte = sorted({t["projekt"] for t in d["tickets"] if t["projekt"]}, key=lambda p: Path(p).name.lower())
    return {"spalten": list(SPALTEN), "tickets": tickets,
            "projekte": [{"pfad": p, "name": Path(p).name} for p in projekte]}


# ---------- Für den Assistenten ----------
def regeln() -> str:
    """Fester Teil im Systemprompt (bleibt im Zwischenspeicher): wie Commits zu
    Tickets werden, und dass Neu tabu ist, bis der Nutzer etwas sagt."""
    cli = Path(__file__).resolve().parent.parent / "tickets.py"
    wer = cfg.user_name()
    return cfg.L(
        f"""## Tickets
Jeder deiner Commits wird zu einer Karte auf dem Ticket-Board (Neu → In Arbeit → In Review → QA → Done; gepusht = Done). Halte den Commit-Betreff kurz (höchstens 60 Zeichen), er wird zum Titel. Arbeitest du an einem Ticket, schreib `T-<Nummer>` in die Commit-Nachricht.
Tickets in „Neu“ fasst du nur an, wenn {wer} es sagt. Board: `python3 "{cli}"` (list / show / move / new — ohne Argumente = Hilfe).""",
        f"""## Tickets
Each of your commits becomes a card on the ticket board (New → In progress → In review → QA → Done; pushed = Done). Keep the commit subject short (60 characters at most), it becomes the title. When you work on a ticket, put `T-<number>` in the commit message.
Only touch tickets in "New" when {wer} says so. Board: `python3 "{cli}"` (list / show / move / new — no arguments = help).""")
