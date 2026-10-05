#!/usr/bin/env python3
"""Eine Firma aus FACTORIA nach CONSTRUCT (Team-Modus) übernehmen.

    python3 scripts/firma_migrieren.py --aus ~/projects/factoria            # nur zeigen
    python3 scripts/firma_migrieren.py --aus ~/projects/factoria --ausfuehren

Was geschieht (und ist nach `--ausfuehren` in `firma/` zu finden):

  * Mitarbeiter: alle Akten aus agents/ — samt SOUL, Gedächtnis, Historie und Zeiger
    auf ihr Direktgespräch (chat.json). Die Geschäftsführung (--chef-aus, Vorgabe
    lumina) wird zu `chef`: ihre Akte, ihr Gedächtnis und ihre Historie ziehen um;
    der Name kommt künftig aus ⚙ Einstellungen (Name des Assistenten). Wer in
    --verwerfen steht (Vorgabe chanti), wird nicht übernommen — sein Gedächtnis und
    seine Historie wandern an den Chef, damit nichts verloren geht.
  * `reports_to` zeigt danach auf `chef`.
  * Anleitungen, bisherige Aufträge (mit umbenannten Absendern) und die Regelwerke
    (HAUSSTIL, PROTOCOL, GESTALTUNG, MODELS) als Überschreibungen unter firma/ —
    dann gelten für die Firma dieselben Regeln wie bisher, auch wenn die
    mitgelieferten Vorlagen sich ändern.
  * Bilder der Mitarbeiter (/uploads/…) wandern in den uploads/-Ordner dieser
    Installation.
  * USER.md bleibt die dieser Installation (eine Person, eine Datei).

Nichts im Quellordner wird verändert. Bestehende Dateien in firma/ werden nicht
überschrieben, außer es steht --ersetzen da.
"""
import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEFAULT_SOUL = BASE / "server" / "team" / "vorlagen" / "agents.default" / "chef" / "SOUL.md"


def lesen(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def frontmatter_setzen(text: str, key: str, wert: str) -> str:
    if re.search(rf"^{key}:", text, re.M):
        return re.sub(rf"^{key}:.*$", f"{key}: {wert}", text, count=1, flags=re.M)
    return text.replace("\n---\n", f"\n{key}: {wert}\n---\n", 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aus", required=True, help="Ordner der FACTORIA-Installation")
    ap.add_argument("--nach", default=str(BASE / "firma"), help="Ziel (Vorgabe: firma/ hier)")
    ap.add_argument("--chef-aus", default="lumina", help="Wessen Akte zur Geschäftsführung wird")
    ap.add_argument("--verwerfen", default="chanti", help="Mitarbeiter, die nicht mitkommen (kommagetrennt)")
    ap.add_argument("--chef-soul", default="", help="Datei mit dem Charakter der Geschäftsführung "
                                                   "(Vorgabe: die Vorlage; {name} wird eingesetzt)")
    ap.add_argument("--ausfuehren", action="store_true", help="wirklich kopieren (sonst nur zeigen)")
    ap.add_argument("--ersetzen", action="store_true", help="vorhandene Dateien überschreiben")
    args = ap.parse_args()

    quelle, ziel = Path(args.aus).expanduser().resolve(), Path(args.nach).expanduser().resolve()
    if not (quelle / "agents").is_dir():
        sys.exit(f"!! {quelle}/agents gibt es nicht.")
    verwerfen = {x.strip() for x in args.verwerfen.split(",") if x.strip()}
    chef_quelle = args.chef_aus
    tu = args.ausfuehren
    plan: list[str] = []

    def kopieren(a: Path, b: Path):
        if b.exists() and not args.ersetzen:
            plan.append(f"  (vorhanden, bleibt) {b.relative_to(ziel)}")
            return
        plan.append(f"  {b.relative_to(ziel)}")
        if tu:
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(a, b)

    def schreiben(b: Path, text: str):
        if b.exists() and not args.ersetzen:
            plan.append(f"  (vorhanden, bleibt) {b.relative_to(ziel)}")
            return
        plan.append(f"  {b.relative_to(ziel)}")
        if tu:
            b.parent.mkdir(parents=True, exist_ok=True)
            b.write_text(text, encoding="utf-8")

    namen = {chef_quelle: "chef", **{v: "chef" for v in verwerfen}}

    def umbenennen(text: str) -> str:
        for alt, neu in namen.items():
            text = re.sub(rf"(?m)^(reports_to:\s*){re.escape(alt)}\s*$", rf"\g<1>{neu}", text)
            # delegates_to: kommagetrennte Liste — den Namen als ganzes Wort ersetzen
            text = re.sub(rf"(?m)^(delegates_to:.*?)\b{re.escape(alt)}\b", rf"\g<1>{neu}", text)
        return text

    # ---- Mitarbeiter
    print("Mitarbeiter")
    uploads_noetig: set[str] = set()
    for d in sorted((quelle / "agents").iterdir()):
        if not (d / "AGENT.md").is_file():
            continue
        slug = d.name
        if slug in verwerfen:
            print(f"  {slug}: wird nicht übernommen (Gedächtnis und Historie gehen an den Chef)")
            continue
        ziel_slug = "chef" if slug == chef_quelle else slug
        zd = ziel / "agents" / ziel_slug
        akte = umbenennen(lesen(d / "AGENT.md"))
        if slug == chef_quelle:
            akte = frontmatter_setzen(akte, "slug", "chef")
            akte = frontmatter_setzen(akte, "name", "Chef")       # kommt aus den Einstellungen
        m = re.search(r"^avatar:\s*(/uploads/\S+)", akte, re.M)
        if m:
            uploads_noetig.add(m.group(1))
        schreiben(zd / "AGENT.md", akte)
        if slug == chef_quelle:
            soul = lesen(Path(args.chef_soul)) if args.chef_soul else lesen(DEFAULT_SOUL)
            schreiben(zd / "SOUL.md", soul)
        elif (d / "SOUL.md").is_file():
            kopieren(d / "SOUL.md", zd / "SOUL.md")
        for name in ("VORSTELLUNG.md", "chat.json"):
            if (d / name).is_file():
                kopieren(d / name, zd / name)
        if slug != chef_quelle:
            for name in ("MEMORY.md", "HISTORIE.jsonl"):
                if (d / name).is_file():
                    kopieren(d / name, zd / name)

    # ---- Chef: Gedächtnis und Historie aus Chef-Quelle und Verworfenen
    cd = ziel / "agents" / "chef"
    gedaechtnis = lesen(quelle / "agents" / chef_quelle / "MEMORY.md").rstrip("\n")
    historie = lesen(quelle / "agents" / chef_quelle / "HISTORIE.jsonl")
    for v in sorted(verwerfen):
        hv = lesen(quelle / "agents" / v / "HISTORIE.jsonl")
        if hv:
            historie += ("\n" if historie and not historie.endswith("\n") else "") + hv
    hinweis = (f"- {date.today().strftime('%d.%m.%Y')}: Die frühere Mitarbeiterin "
               f"{', '.join(sorted(verwerfen)) or 'Chanti'} gibt es in der Firma nicht mehr — du selbst bist jetzt "
               f"die Geschäftsführung und zugleich der Assistent, mit dem der Nutzer im Chat redet. Aufgaben, die an sie "
               f"gingen (Inhalte sammeln, recherchieren, Texte schreiben), vergibst du an jemanden, der das kann, "
               f"oder stellst jemanden ein. Namen in diesem Gedächtnis, die auf sie zeigen, sind historisch.")
    schreiben(cd / "MEMORY.md", (gedaechtnis + "\n" if gedaechtnis else "") + hinweis + "\n")
    if historie.strip():
        schreiben(cd / "HISTORIE.jsonl", historie)
    if not (quelle / "agents" / chef_quelle / "AGENT.md").is_file():
        print(f"!! {chef_quelle} hat keine Akte — es gibt dann keinen Chef; die Vorlage wird beim Start angelegt.")

    # ---- Anleitungen, Regelwerke
    print("\nAnleitungen")
    for d in sorted((quelle / "anleitungen").glob("*/ANLEITUNG.md")) if (quelle / "anleitungen").is_dir() else []:
        kopieren(d, ziel / "anleitungen" / d.parent.name / "ANLEITUNG.md")
    print("\nRegelwerke")
    for name in ("HAUSSTIL.md", "PROTOCOL.md", "GESTALTUNG.md", "MODELS.md"):
        if (quelle / name).is_file():
            text = lesen(quelle / name)
            # Zwei Stellen, die auf FACTORIA zeigen und sonst ins Leere liefen.
            text = text.replace("factoria_mcp.py", "team_mcp.py").replace("Cody, er baut Factoria", "Cody, er baut die Firma")
            text = text.replace("Lumina ist die Geschäftsführerin, Chanti die Assistentin.", "Die Geschäftsführung ist die Assistentin.")
            schreiben(ziel / name, text)

    # ---- Aufträge (mit umbenannten Absendern)
    print("\nAufträge")
    for d in sorted((quelle / "tickets").iterdir()) if (quelle / "tickets").is_dir() else []:
        if not (d / "ticket.json").is_file():
            continue
        zd = ziel / "auftraege" / d.name
        t = json.loads(lesen(d / "ticket.json"))
        if str(t.get("titel", "")).startswith("[eval]"):
            continue                       # Testaufträge des Prüfstands gehören nicht zur Geschichte
        if t.get("owner") in namen:
            t["owner"] = "chef"
        esk = t.get("eskalation")
        if isinstance(esk, dict) and esk.get("an") in namen:
            esk["an"] = "chef"             # sonst ginge die Antwort an eine Akte, die es nicht mehr gibt
        if t.get("status") in ("laeuft", "neu"):
            # Ein Auftrag, der in FACTORIA noch lief, startet hier nicht von allein: seine
            # Sitzung gehörte einer anderen Person. Der Nutzer entscheidet, ob es weitergeht.
            t["status"] = "wartet_auf_kevin"
            t["in_arbeit"] = None
            t["eskalation"] = {"bremse": "neustart", "seit": 0, "an": "chef",
                               "grund": "Dieser Auftrag lief noch, als die Firma aus FACTORIA übernommen wurde.",
                               "frage": "Soll es weitergehen? Dann WEITERMACHEN — oder abbrechen."}
        sessions = t.get("sessions") or {}
        t["sessions"] = {("chef" if k in namen else k): v for k, v in sessions.items()}
        schreiben(zd / "ticket.json", json.dumps(t, ensure_ascii=False, indent=1))
        zeilen = []
        for z in lesen(d / "thread.jsonl").splitlines():
            try:
                e = json.loads(z)
            except ValueError:
                continue
            for k in ("von", "an"):
                if e.get(k) in namen:
                    e[k] = "chef"
            zeilen.append(json.dumps(e, ensure_ascii=False))
        schreiben(zd / "thread.jsonl", "\n".join(zeilen) + ("\n" if zeilen else ""))

    # ---- Bilder
    print("\nBilder der Mitarbeiter")
    for u in sorted(uploads_noetig):
        name = Path(u).name
        src = quelle / "uploads" / name
        dst = BASE / "uploads" / name
        if src.is_file() and (not dst.exists() or args.ersetzen):
            plan.append(f"  uploads/{name}")
            if tu:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        elif not src.is_file():
            plan.append(f"  (fehlt in der Quelle) uploads/{name}")

    print("\n".join(plan))
    print(f"\n{'Kopiert' if tu else 'Würde kopieren'}: {len(plan)} Einträge nach {ziel}"
          + ("" if tu else " — mit --ausfuehren wirklich ausführen."))


if __name__ == "__main__":
    main()
