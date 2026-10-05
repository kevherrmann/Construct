"""Claude-Code-Sessions auf der Platte: Metadaten (Namen, Archiv),
Transkripte lesen, Filter für fremde und versteckte Sessions.
"""
import json
import re

from server.core import BASE_DIR, PROJECTS_DIR, extract_text


SESS_META = BASE_DIR / "sessions_meta.json"


def load_meta() -> dict:
    """sessions_meta.json: {"archived": [ids], "names": {id: eigener Titel}}."""
    try:
        d = json.loads(SESS_META.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_meta(d: dict):
    tmp = SESS_META.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SESS_META)


def load_archived():
    """Set archivierter Session-IDs (nur ausgeblendet, NICHT gelöscht)."""
    return set(load_meta().get("archived", []))


def save_archived(ids):
    meta = load_meta()
    meta["archived"] = sorted(ids)
    save_meta(meta)


# MCP-Server, deren Sitzungen von einer eigenstaendigen Agenten-Anwendung
# stammen und nicht von einem Gespraech mit Kevin.
#
# Warum es das braucht: FACTORIA arbeitet im selben Projektordner und legt pro
# Agentenzug eine eigene Claude-Code-Sitzung an. Gemessen am 04.09.2026 kamen
# 46 von 55 Eintraegen in dieser Uebersicht von dort — Kevins eigene Gespraeche
# gingen darin unter.
#
# Erkannt wird am MCP-Praefix in der WERKZEUGLISTE des Laufs, nicht am Text:
# ein Gespraech ueber Factoria (wie dieses hier) nennt den Namen auch, hat aber
# nie `mcp__factoria__*` als Werkzeug bekommen. Und die Liste steht im
# Transkript, egal ob der Agent die Werkzeuge am Ende benutzt hat — auch ein
# Zug, der nichts an den Bus gab, wird so erkannt.
# "firma" ist der Bus des Team-Modus (server/team/); "factoria" die Sitzungen aus
# der Zeit, als die Firma noch ein eigenes Programm war.
FREMDE_MCP = ("firma", "factoria")


MCP_RE = re.compile(r"^mcp__([a-z0-9_-]+)__")


# Arbeitsordner, deren Sitzungen gar nicht erst in der Uebersicht auftauchen.
# /tmp ist ein Wegwerfordner: dort landen Testlaeufe (auch von FACTORIA und vom
# Pruefstand), an denen Kevin nie weiterarbeitet. Sie werden uebersprungen und
# nicht bloss ausgeblendet — anders als die Sitzungen der Firma, die man sich
# mit dem Schalter noch ansehen koennen soll.
VERBORGENE_CWDS = ("/tmp",)


def _verborgen(cwd: str) -> bool:
    c = (cwd or "").rstrip("/")
    return any(c == v or c.startswith(v + "/") for v in VERBORGENE_CWDS)


# Der zweite Weg. Nicht jeder fremde Lauf hat einen Bus: FACTORIA startet fuer
# sich selbst auch werkzeuglose Laeufe (Gespraech verdichten, Gedaechtnis
# eindicken), und die saehen hier aus wie ein Gespraech von Kevin. Sie setzen
# deshalb eine Kennzeile an den Anfang ihres Prompts, die im Transkript landet.
# Das ist ein Textmerkmal — aber eines, das die andere Seite absichtlich setzt,
# und kein Erraten anhand des Inhalts.
INTERN_MARKEN = {"[firma-intern]": "firma", "[factoria-intern]": "factoria"}


def _fremde_firma(ev: dict) -> str:
    """Von welcher Agenten-Anwendung stammt dieser Lauf? "" = von Kevin."""
    if ev.get("type") == "attachment":
        att = ev.get("attachment") or {}
        if att.get("type") == "deferred_tools_delta":
            for n in (att.get("addedNames") or []):
                m = MCP_RE.match(str(n))
                if m and m.group(1) in FREMDE_MCP:
                    return m.group(1)
        return ""
    if ev.get("type") == "user":
        txt = extract_text(ev.get("message", {}).get("content")).lstrip()
        for marke, firma in INTERN_MARKEN.items():
            if txt.startswith(marke):
                return firma
    return ""


# Die Ticket-Zeile, die an Kevins Nachricht hängt (tickets.hinweis): für den
# Assistenten, nicht für die Anzeige.
TICKETZEILE_RE = re.compile(r"\n\n\[Tickets: [\s\S]*?\]\s*$")


def ohne_ticketmarker(txt: str) -> str:
    """Antwort des Assistenten ohne die Markerzeilen am Ende (`[[ticket neu: …]]`)."""
    from server.tickets import marken_am_ende
    return marken_am_ende(txt)[0].strip() if "[[ticket" in txt else txt


def ohne_ticketzeile(txt: str) -> str:
    """Nutzertext aus einem Transkript ohne die Ticket-Zeile am Ende — für
    Titel, Anzeige und alles, was Kevins Worte lesen soll."""
    return TICKETZEILE_RE.sub("", txt)


def _parse_transcript_lines(data: bytes):
    """JSONL-Bytes -> Anzeige-Nachrichten (wie die Verlaufs-Ansicht sie braucht)."""
    msgs = []
    for line in data.split(b"\n"):
        if not line.strip():
            continue
        try:
            ev = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        t = ev.get("type")
        if t not in ("user", "assistant"):
            continue
        txt = extract_text(ev.get("message", {}).get("content")).strip()
        # Meta-Rauschen fremder Sessions (System-Reminder, CLI-Wrapper) ausblenden
        if not txt or (t == "user" and (txt.startswith("<") or txt.startswith("Caveat"))):
            continue
        if t == "user":
            txt = ohne_ticketzeile(txt)
        else:
            txt = ohne_ticketmarker(txt)
            if not txt:
                continue
        m = {"role": t, "text": txt}
        if isinstance(ev.get("uuid"), str):
            m["uuid"] = ev["uuid"]            # Anker für Tickets: dorthin springt die Übersicht
        if isinstance(ev.get("timestamp"), str):
            m["ts"] = ev["timestamp"]     # ISO-Zeit, die UI zeigt sie neben der Nachricht
        msgs.append(m)
    return msgs


SCHREIB_WERKZEUGE = ("Write", "Edit", "MultiEdit", "NotebookEdit")
BEFEHL_WERKZEUGE = ("Bash",)


def _ergebnis_text(content) -> str:
    """tool_result-Inhalt (String oder Block-Liste) -> Text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def werkstatt_aus_transcript(data: bytes, max_befehle: int = 80) -> dict:
    """Was in einer Session an Dateien geschrieben und im Terminal ausgeführt
    wurde — für Werkbank und Fernseher im Construct-Raum. Der Verlauf, den die
    Oberfläche beim Öffnen lädt, enthält nur Text; die Werkzeuge stehen hier.

    dateien: je Pfad einmal, neueste zuletzt; befehle: die letzten max_befehle
    mit gekürzter Ausgabe; cwd: Arbeitsordner der Session.
    """
    dateien: dict[str, dict] = {}
    befehle: list[dict] = []
    offen: dict[str, dict] = {}
    cwd = ""
    for line in data.split(b"\n"):
        if not line.strip():
            continue
        try:
            ev = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        if not cwd and isinstance(ev.get("cwd"), str):
            cwd = ev["cwd"]
        content = ev.get("message", {}).get("content") if isinstance(ev.get("message"), dict) else None
        if not isinstance(content, list):
            continue
        ts = ev.get("timestamp") if isinstance(ev.get("timestamp"), str) else ""
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                name, inp = b.get("name", ""), b.get("input") or {}
                if name in SCHREIB_WERKZEUGE:
                    pfad = inp.get("file_path") or inp.get("notebook_path") or inp.get("path")
                    if isinstance(pfad, str) and pfad:
                        alt = dateien.pop(pfad, None)
                        dateien[pfad] = {"path": pfad, "neu": (alt or {}).get("neu", name == "Write"),
                                         "mal": (alt or {}).get("mal", 0) + 1, "ts": ts}
                elif name in BEFEHL_WERKZEUGE and isinstance(inp.get("command"), str):
                    eintrag = {"command": inp["command"], "description": inp.get("description") or "",
                               "output": None, "isError": False, "ts": ts}
                    befehle.append(eintrag)
                    if b.get("id"):
                        offen[b["id"]] = eintrag
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in offen:
                eintrag = offen.pop(b["tool_use_id"])
                eintrag["output"] = _ergebnis_text(b.get("content"))[-4000:]
                eintrag["isError"] = bool(b.get("is_error"))
    return {"cwd": cwd, "dateien": list(dateien.values()), "befehle": befehle[-max_befehle:]}


def model_short(mid: str) -> str:
    """Modell-ID aus einem Transkript -> der Wert, den die Auswahlliste kennt.

    Frueher wurde hier auf die Reihe verkuerzt (claude-fable-5-1 -> "fable").
    Damit ging genau die Angabe verloren, um die es geht: WELCHES Fable. Die
    Oberflaeche fuehrt inzwischen volle IDs, also wird die ID durchgereicht und
    nur um das bereinigt, was nicht zur Auswahl gehoert — der Datumsstempel
    (claude-haiku-4-5-20251001) und der Kontext-Zusatz (…[1m]).

    Unbekanntes/synthetisches -> "" (= Konto-Standard).
    """
    m = (mid or "").lower().strip()
    m = re.sub(r"\[[^\]]*\]$", "", m)          # …[1m]
    if not m.startswith("claude-"):
        return ""
    m = re.sub(r"-\d{8}$", "", m)              # …-20251001
    return m


def _last_model(data: bytes) -> str:
    """Das zuletzt in DIESER Session tatsächlich genutzte Modell (aus der letzten
    Assistant-Nachricht). So zeigt die UI beim Öffnen das Session-Modell an."""
    for line in reversed(data.split(b"\n")):
        if not line.strip() or b'"model"' not in line:
            continue
        try:
            ev = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        if ev.get("type") == "assistant":
            short = model_short(ev.get("message", {}).get("model", ""))
            if short:
                return short
    return ""


SID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def find_prompt(session_id: str, text: str, occurrence: int = 0):
    """Eine eigene Nachricht im Transkript wiederfinden — fürs Bearbeiten.

    Gesucht wird die `occurrence`-te Nutzer-Nachricht (0 = erste) mit genau
    diesem Text; angehängte Datei-Hinweise hinter dem Text zählen mit dazu.
    Liefert (uuid, parentUuid) — an parentUuid setzt der neue Lauf wieder an
    (--resume-session-at), die Nachricht selbst und alles danach fallen weg.
    parentUuid ist None, wenn es die allererste Nachricht war.
    Nicht gefunden → None.
    """
    if not SID_RE.match(session_id or ""):
        return None
    f = next(iter(PROJECTS_DIR.glob(f"*/{session_id}.jsonl")), None)
    if f is None:
        return None
    want = (text or "").strip()
    seen = 0
    for line in f.read_bytes().split(b"\n"):
        try:
            ev = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        if ev.get("type") != "user" or not ev.get("uuid"):
            continue
        got = extract_text(ev.get("message", {}).get("content")).strip()
        if got == want or got.startswith(want + "\n\n["):
            if seen == occurrence:
                return ev["uuid"], ev.get("parentUuid")
            seen += 1
    return None



def nutzer_uuids_bis(session_id: str, bis_uuid: str) -> set:
    """Uuids aller Nutzer-Nachrichten, die in der Session VOR der Zeile mit
    bis_uuid stehen — das, was eine abgezweigte Session (--resume-session-at)
    von ihrer Vorgängerin behält."""
    f = next(iter(PROJECTS_DIR.glob(f"*/{session_id}.jsonl")), None) if SID_RE.match(session_id or "") else None
    out: set = set()
    if f is None:
        return out
    for line in f.read_bytes().split(b"\n"):
        try:
            ev = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        if ev.get("type") == "user" and ev.get("uuid"):
            out.add(ev["uuid"])
        if ev.get("uuid") == bis_uuid:
            break          # die Zeile selbst bleibt (ist sie eine Nutzer-Nachricht, steht sie schon drin)
    return out


def nachrichtentexte(session_id: str, uuids: set) -> dict:
    """uuid → voller Text von Nutzer-Nachrichten einer Session (ohne Ticket-Zeile
    und Datei-Hinweise). Die Ticket-Datei kennt nur Auszüge; für ein Briefing an die
    Firma braucht es den Wortlaut."""
    out: dict = {}
    f = next(iter(PROJECTS_DIR.glob(f"*/{session_id}.jsonl")), None) if SID_RE.match(session_id or "") else None
    if f is None:
        return out
    for line in f.read_bytes().split(b"\n"):
        try:
            ev = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        if ev.get("type") == "user" and ev.get("uuid") in uuids:
            txt = ohne_ticketzeile(extract_text(ev.get("message", {}).get("content")).strip())
            out[ev["uuid"]] = re.sub(r"\n\n\[(?:Vom Nutzer hochgeladene|Image uploaded|PDF uploaded)[\s\S]*$", "", txt).strip()
    return out
