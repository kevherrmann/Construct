#!/usr/bin/env python3
"""
tickets.py — das Ticket-Board von der Kommandozeile (für den Assistenten).

Dieselbe Datei wie die Oberfläche: tickets/board.json (server/tickets.py).

  python3 tickets.py list [spalte] [--projekt name]   Karten (ohne Done, außer danach gefragt)
  python3 tickets.py show 12                          eine Karte mit Text und Commits
  python3 tickets.py move 12 arbeit                   verschieben (neu/arbeit/review/qa/done)
  python3 tickets.py new "Titel" ["Text"] [--projekt /pfad] [--spalte neu]
  python3 tickets.py title 12 "Neuer Titel"
  python3 tickets.py text 12 "Neuer Text"

Spalten: neu (Neu), arbeit (In Arbeit), review (In Review), qa (QA), done (Done).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server import tickets as tk  # noqa: E402

NAMEN = {"neu": "Neu", "arbeit": "In Arbeit", "review": "In Review", "qa": "QA", "done": "Done"}
# Englische und sprechende Namen für dieselben Spalten
ALIAS = {"new": "neu", "todo": "neu", "work": "arbeit", "progress": "arbeit", "doing": "arbeit",
         "in-arbeit": "arbeit", "in_progress": "arbeit", "in-review": "review"}


def _spalte(s: str) -> str:
    s = (s or "").strip().lower()
    s = ALIAS.get(s, s)
    if s not in tk.SPALTEN:
        sys.exit(f"Unbekannte Spalte '{s}'. Möglich: {', '.join(tk.SPALTEN)}")
    return s


def _opt(args: list, name: str) -> str:
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            wert = args[i + 1]
            del args[i:i + 2]
            return wert
        del args[i]
    return ""


def _zeile(t: dict) -> str:
    projekt = Path(t["projekt"]).name if t["projekt"] else "-"
    extra = f" · {len(t['commits'])} Commit(s)" if t["commits"] else ""
    return f"T-{t['nr']:<4} [{NAMEN[t['spalte']]}] {t['titel']}  ({projekt}{extra})"


def main(argv: list) -> int:
    if not argv:
        print(__doc__.strip())
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        projekt = _opt(args, "--projekt")
        spalte = _spalte(args[0]) if args else ""
        tickets = [t for t in tk.laden()["tickets"]
                   if (t["spalte"] == spalte if spalte else t["spalte"] != "done")
                   and (not projekt or Path(t["projekt"]).name == projekt or t["projekt"] == projekt)]
        if not tickets:
            print("Keine Tickets.")
        for t in sorted(tickets, key=lambda x: (tk.SPALTEN.index(x["spalte"]), x["nr"])):
            print(_zeile(t))
        return 0
    if cmd == "show" and args:
        t = tk.holen(args[0].lstrip("Tt-"))
        if not t:
            sys.exit("Dieses Ticket gibt es nicht.")
        print(_zeile(t))
        if t["projekt"]:
            print(f"Projekt: {t['projekt']}")
        if t["auftrag"]:
            print(f"Firma-Auftrag: {t['auftrag']}")
        if t["text"]:
            print("\n" + t["text"])
        for c in t["commits"]:
            print(f"  {c['sha'][:8]} {c['branch']}: {c['betreff']}" + (" (gepusht)" if c["gepusht"] else ""))
        return 0
    if cmd == "move" and len(args) >= 2:
        try:
            t = tk.aendern(args[0].lstrip("Tt-"), spalte=_spalte(args[1]))
        except KeyError:
            sys.exit("Dieses Ticket gibt es nicht.")
        print("✓ " + _zeile(t))
        return 0
    if cmd == "new" and args:
        projekt = _opt(args, "--projekt")
        spalte = _spalte(_opt(args, "--spalte") or "neu")
        t = tk.anlegen(args[0], args[1] if len(args) > 1 else "", projekt, spalte, von="assistent")
        print("✓ " + _zeile(t))
        return 0
    if cmd in ("title", "text") and len(args) >= 2:
        try:
            t = tk.aendern(args[0].lstrip("Tt-"), **({"titel": args[1]} if cmd == "title" else {"text": args[1]}))
        except KeyError:
            sys.exit("Dieses Ticket gibt es nicht.")
        print("✓ " + _zeile(t))
        return 0
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
