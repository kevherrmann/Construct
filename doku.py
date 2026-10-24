#!/usr/bin/env python3
"""Dokumente-Ablage auf der Kommandozeile, vor allem für den Assistenten.

  doku.py inbox                         was noch einsortiert werden muss
  doku.py search "grundsteuer 2023"     Volltextsuche (Titel, Absender, Inhalt)
  doku.py show 12 [--chars 6000]        Angaben und gelesener Text
  doku.py set 12 --title "…" --date 2023-01-23 --sender "Finanzamt" \\
                 --type Bescheid --tags Steuer,Haus --done
  doku.py split 12 "1-2, 3, 4-6"          in mehrere Dokumente aufteilen
  doku.py names                         Absender, Typen, Tags mit Anzahl
  doku.py wait                          warten, bis alles gelesen ist
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.dokumente import ablage  # noqa: E402

# Die CLI liest selbst (split, wait): ein Hintergrund-Thread stürbe mit ihr
ablage.HINTERGRUND = False


def zeile(d: dict) -> str:
    tags = ",".join(t["name"] for t in d["tags"])
    teile = [f"#{d['id']}", d["datum"] or "----------", d["absender"] or "?", d["typ"] or "?",
             d["titel"] or "(ohne Titel)"]
    if tags:
        teile.append(f"[{tags}]")
    if d["zustand"] != "fertig":
        teile.append(f"<{d['zustand']}>")
    if d["hinweis"]:
        teile.append(f"({d['hinweis']})")
    return "  ".join(teile)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="doku.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inbox")
    s = sub.add_parser("search")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--year", default="")
    s.add_argument("--limit", type=int, default=50)
    sh = sub.add_parser("show")
    sh.add_argument("id", type=int)
    sh.add_argument("--chars", type=int, default=6000)
    st = sub.add_parser("set")
    st.add_argument("id", type=int)
    st.add_argument("--title")
    st.add_argument("--date")
    st.add_argument("--sender")
    st.add_argument("--type")
    st.add_argument("--tags", help="Komma-getrennt, ersetzt die bisherigen")
    st.add_argument("--note")
    st.add_argument("--done", action="store_true", help="aus dem Eingang nehmen (bestätigt)")
    sp = sub.add_parser("split")
    sp.add_argument("id", type=int)
    sp.add_argument("seiten")
    sub.add_parser("names")
    w = sub.add_parser("wait")
    w.add_argument("--timeout", type=int, default=600)
    a = p.parse_args(argv)

    try:
        if a.cmd == "inbox":
            ds = ablage.liste(eingang=True, limit=500)["dokumente"]
            print("\n".join(zeile(d) for d in ds) if ds else "Eingang ist leer.")
        elif a.cmd == "search":
            r = ablage.liste(q=a.query, jahr=a.year, limit=a.limit)
            print(f"{r['gesamt']} Treffer")
            for d in r["dokumente"]:
                print(zeile(d))
        elif a.cmd == "show":
            d = ablage.dokument(a.id)
            print(zeile(d))
            print(f"Seiten: {d['seiten']}  Datei: {d['datei']}")
            if d["notiz"]:
                print(f"Notiz: {d['notiz']}")
            print("--- Text ---")
            text = d["text"].replace("\f", "\n--- Seitenwechsel ---\n")
            print(text[:a.chars] + ("\n[…gekürzt]" if len(text) > a.chars else ""))
        elif a.cmd == "set":
            f = {}
            for arg, feld in (("title", "titel"), ("date", "datum"), ("sender", "absender"),
                              ("type", "typ"), ("note", "notiz")):
                v = getattr(a, arg)
                if v is not None:
                    f[feld] = v
            if a.tags is not None:
                f["tags"] = [t.strip() for t in a.tags.split(",") if t.strip()]
            if a.done:
                f["eingang"] = False
            print(zeile(ablage.aendern(a.id, f)))
        elif a.cmd == "split":
            for d in ablage.teilen(a.id, a.seiten):
                print(zeile(d))
            ablage.HINTERGRUND = False
            ablage.jetzt_lesen_alle()
        elif a.cmd == "names":
            for tab, titel in (("absender", "Absender"), ("typen", "Typen"), ("tags", "Tags")):
                print(f"{titel}: " + ", ".join(f"{n['name']} ({n['anzahl']})" for n in ablage.namen(tab)))
        elif a.cmd == "wait":
            ende = time.time() + a.timeout
            while ablage.uebersicht()["lesen"] and time.time() < ende:
                time.sleep(2)
            print(f"noch in Arbeit: {ablage.uebersicht()['lesen']}")
    except KeyError:
        print("Dokument gibt es nicht.", file=sys.stderr)
        return 1
    except ablage.Fehler as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
