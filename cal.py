#!/usr/bin/env python3
"""
cal.py — Codys Kalender. Kleine, robuste Termin-Verwaltung.

Eine einzige Wahrheit: events.json (neben dieser Datei) — genau die Datei, die
auch die Matrix-Weboberfläche anzeigt. Dieses Modul wird von app.py & dem
Telegram-Bot importiert UND von Cody als CLI benutzt.

CLI (so trägt Cody Termine ein):
  python3 cal.py add 2026-06-28 15:00 "Zahnarzt" ["Notiz"]
  python3 cal.py add 2026-06-28 "Geburtstag Oma"     # ohne Uhrzeit = ganztägig
  python3 cal.py list [2026-06]                       # alle oder ein Monat
  python3 cal.py upcoming [tage]                      # default 7 Tage
  python3 cal.py today
  python3 cal.py rm <id>

Termin-Format (events.json = Liste solcher Objekte):
  {"id":"a1b2c3d4","date":"2026-06-28","time":"15:00","title":"Zahnarzt",
   "notes":"","created":"2026-06-27T18:40:00"}
  time == "" bedeutet ganztägig.
"""
import json
import os
import re
import sys
import uuid
import datetime
from pathlib import Path

EVENTS_FILE = Path(__file__).parent / "events.json"
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")
_DE_DOW = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_EN_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------- Lesen / Schreiben (atomar) ----------
def load_events():
    try:
        data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_events(events):
    """Sortiert (Datum, Uhrzeit) und schreibt atomar, damit die Datei nie halb-kaputt ist."""
    events = sorted(events, key=lambda e: (e.get("date", ""), e.get("time", "")))
    tmp = EVENTS_FILE.with_name(EVENTS_FILE.name + ".tmp")
    tmp.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(EVENTS_FILE)
    return events


def add_event(date, title, time="", notes="", repeat="", prompt=""):
    ev = {
        "id": uuid.uuid4().hex[:8],
        "date": (date or "").strip(),
        "time": (time or "").strip(),
        "title": (title or "").strip(),
        "notes": (notes or "").strip(),
        "repeat": (repeat or "").strip(),   # "" = einmalig, "yearly" = jährlich (z.B. Geburtstag)
        "prompt": (prompt or "").strip(),   # geplante Cody-Aufgabe: läuft zur Termin-Zeit (Ergebnis per Telegram)
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    events = load_events()
    events.append(ev)
    save_events(events)
    return ev


def remove_event(eid):
    events = load_events()
    keep = [e for e in events if e.get("id") != eid]
    save_events(keep)
    return len(events) - len(keep)


# ---------- Abfragen ----------
def _occurs_on(e, day):
    """Findet das Event an einem konkreten Tag statt? (berücksichtigt jährliche Wiederholung)"""
    d = e.get("date", "")
    if len(d) < 10:
        return False
    if e.get("repeat") == "yearly":
        return d[5:] == day.isoformat()[5:]   # gleicher Monat-Tag, Jahr egal
    return d == day.isoformat()


def events_on(day):
    """Alle Termine an einem Tag — Wiederholungen auf diesen Tag „materialisiert“ (date = day)."""
    ds = day.isoformat()
    out = []
    for e in load_events():
        if _occurs_on(e, day):
            occ = dict(e)
            occ["date"] = ds
            out.append(occ)
    return sorted(out, key=lambda e: e.get("time", ""))


def upcoming(days=7, today=None):
    """Termine von heute bis +days Tage — Wiederholungen auf ihr nächstes Vorkommen aufgelöst."""
    today = today or datetime.date.today()
    out = []
    for i in range(days + 1):
        out.extend(events_on(today + datetime.timedelta(days=i)))
    return sorted(out, key=lambda e: (e.get("date", ""), e.get("time", "")))


def context_block(days=7, today=None):
    """Kalender-Block für Codys System-Prompt — frisch bei jeder Anfrage eingespielt.

    Dadurch *weiß* Cody jederzeit, was ansteht, und kann von sich aus erinnern.
    Dazu die Anleitung fürs Eintragen samt ECHTEM Pfad dieser Datei: fest in
    der Persona stünde er nur für einen Rechner richtig.
    """
    today = today or datetime.date.today()
    try:
        import config
        en = config.lang() == "en"
    except Exception:
        en = False
    dow = _EN_DOW if en else _DE_DOW
    if en:
        head = f"## Your calendar (today is {dow[today.weekday()]}, {today.isoformat()})"
    else:
        head = f"## Dein Kalender (heute ist {dow[today.weekday()]}, {today.isoformat()})"
    ups = upcoming(days, today)
    if not ups:
        return head + (f"\nNo events in the next {days} days." if en
                       else f"\nKeine Termine in den nächsten {days} Tagen eingetragen.") + _cli_help(en)
    lines = [head, "Upcoming events — remind the user of them yourself when it fits:" if en
             else "Anstehende Termine — erinnere den Nutzer von dir aus daran, wenn es gerade passt:"]
    for e in ups:
        d = datetime.date.fromisoformat(e["date"])
        delta = (d - today).days
        if delta == 0:
            when = "TODAY" if en else "HEUTE"
        elif delta == 1:
            when = "tomorrow" if en else "morgen"
        else:
            when = f"{dow[d.weekday()]} {d.isoformat() if en else d.strftime('%d.%m.')}"
        t = (" " + e["time"]) if e.get("time") else ""
        note = f" — {e['notes']}" if e.get("notes") else ""
        lines.append(f"- {when}{t}: {e['title']}{note}")
    return "\n".join(lines) + _cli_help(en)


def _cli_help(en: bool) -> str:
    """Wie Cody Termine selbst verwaltet — mit dem Pfad dieser Installation."""
    py = "python" if os.name == "nt" else "python3"
    me = str(Path(__file__).resolve())
    c = f'{py} "{me}"'
    if en:
        return ("\n\nManage events yourself with this CLI (the interface shows them right away):\n"
                f'- add: `{c} add YYYY-MM-DD [HH:MM] "Title" ["Note"]` — without a time = all day; '
                "`--yearly` repeats every year (then MM-DD is enough)\n"
                f"- look up: `{c} upcoming [days]`, `{c} today`, `{c} list [YYYY-MM]`\n"
                f"- delete: `{c} rm <id>` (id from `list`)\n"
                "Convert relative dates (\"tomorrow\", \"next Friday\") to a date yourself, "
                "and briefly confirm what you did.")
    return ("\n\nTermine verwaltest du selbst mit diesem CLI (die Oberfläche zeigt sie sofort an):\n"
            f'- eintragen: `{c} add JJJJ-MM-TT [HH:MM] "Titel" ["Notiz"]` — ohne Uhrzeit = ganztägig; '
            "`--yearly` wiederholt jährlich (dann reicht MM-TT)\n"
            f"- nachsehen: `{c} upcoming [tage]`, `{c} today`, `{c} list [JJJJ-MM]`\n"
            f"- löschen: `{c} rm <id>` (ID aus `list`)\n"
            "Relative Angaben („morgen“, „nächsten Freitag“) rechnest du selbst aufs Datum um "
            "und bestätigst kurz, was du gemacht hast.")


# ---------- CLI ----------
def _fmt(e):
    t = e.get("time") or "ganztägig"
    note = f"  ({e['notes']})" if e.get("notes") else ""
    rep = "  🔁 jährlich" if e.get("repeat") == "yearly" else ""
    return f"{e.get('date')}  {t:<9}  {e.get('title', '')}{note}{rep}  [{e.get('id')}]"


def _cli(argv):
    if not argv:
        print(__doc__.strip())
        return 0
    cmd = argv[0].lower()

    if cmd == "add":
        rest = argv[1:]
        # --yearly / -y irgendwo in den Argumenten -> jährlich wiederkehrend
        repeat = "yearly" if any(a in ("--yearly", "-y") for a in rest) else ""
        rest = [a for a in rest if a not in ("--yearly", "-y")]
        if len(rest) < 2:
            print('Nutzung: cal.py add [--yearly] YYYY-MM-DD [HH:MM] "Titel" ["Notiz"]')
            print('         (bei --yearly ist auch MM-DD ohne Jahr erlaubt)')
            return 1
        date = rest[0]
        if repeat == "yearly" and re.match(r"^\d{2}-\d{2}$", date):
            date = f"{datetime.date.today().year}-{date}"   # Jahr ist bei jährlich nur Anker
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            print(f"Ungültiges Datum: {date} (erwartet YYYY-MM-DD bzw. MM-DD bei --yearly)")
            return 1
        rest = rest[1:]
        time = ""
        if rest and _TIME_RE.match(rest[0]):
            time, rest = rest[0], rest[1:]
        if not rest:
            print("Kein Titel angegeben.")
            return 1
        title = rest[0]
        notes = rest[1] if len(rest) > 1 else ""
        print("✓ eingetragen:", _fmt(add_event(date, title, time, notes, repeat)))
        return 0

    if cmd == "rm":
        if len(argv) < 2:
            print("Welche ID? (siehe cal.py list)")
            return 1
        n = remove_event(argv[1])
        print(f"✓ {n} Termin(e) gelöscht." if n else "Keine passende ID gefunden.")
        return 0

    if cmd == "list":
        evs = load_events()
        if len(argv) > 1:
            evs = [e for e in evs if e.get("date", "").startswith(argv[1])]
        if not evs:
            print("(keine Termine)")
            return 0
        for e in sorted(evs, key=lambda e: (e.get("date", ""), e.get("time", ""))):
            print(_fmt(e))
        return 0

    if cmd == "today":
        today = datetime.date.today()
        evs = events_on(today)
        if not evs:
            print(f"Heute ({today.isoformat()}) steht nichts an.")
            return 0
        print(f"Heute ({today.isoformat()}):")
        for e in evs:
            print("  " + _fmt(e))
        return 0

    if cmd == "upcoming":
        days = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 7
        print(context_block(days))
        return 0

    print(f"Unbekannter Befehl: {cmd}")
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
