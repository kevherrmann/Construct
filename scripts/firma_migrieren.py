#!/usr/bin/env python3
"""Eine Firma aus FACTORIA nach CONSTRUCT (Team-Modus) übernehmen.

    python3 scripts/firma_migrieren.py --aus ~/projects/factoria            # nur zeigen
    python3 scripts/firma_migrieren.py --aus ~/projects/factoria --ausfuehren

Was geschieht (und ist nach `--ausfuehren` in `firma/` zu finden):

  * Mitarbeiter: alle Akten aus agents/ — samt Gedächtnis und Historie.
    Die Geschäftsführung (--chef-aus, Vorgabe lumina) wird
    zu `chef`; sie heißt dann für alle wie der Assistent dieser Installation und trägt den
    Namen aus ⚙ Einstellungen. Ihr Foto kommt nicht mit: die Chefin ist die Figur des
    Assistenten.
  * Umbenannt werden (--umbenennen) die Kürzel, die CONSTRUCT mitliefert, damit Raum und
    Vorlagen sie wiederfinden: cody -> luna (Backend; Cody ist jetzt der Assistent und damit
    die Geschäftsführung), css-spezialist -> elara, qa -> miranda, auditor -> janus.
    Wo es zu einem Kürzel einen mitgelieferten Charakter gibt (chef, cody,
    elara, miranda, janus), gelten dieser und der Name aus der Vorlage (Selma heißt jetzt Elara,
    Tessa Miranda, Veritas Janus, die Backend-Stelle Luna); Gedächtnis und Historie bleiben die Factoria-Fassung.
  * Zusammengelegt (--zusammenlegen) wird, wer künftig nicht mehr einzeln arbeitet: chanti
    geht in die Chefin, design (Rauke) in Elara. Akte und Charakter kommen nicht mit, aber
    Gedächtnis und Historie wandern an das Ziel, damit nichts verloren geht.
  * Weggelassen (--weglassen) wird, wen die Firma nicht mehr braucht: druck (3D-Druck).
    Seine Akte kommt nicht mit, und aus `delegates_to` der anderen verschwindet er.
  * `reports_to` zeigt danach auf `chef`; das Einstellen gibt es nicht mehr (`can_hire`
    fällt weg).
  * Anleitungen, bisherige Aufträge (mit umbenannten Absendern) und die Regelwerke
    (HAUSSTIL, PROTOCOL, GESTALTUNG, MODELS) als Überschreibungen unter firma/ —
    dann gelten für die Firma dieselben Regeln wie bisher, auch wenn die
    mitgelieferten Vorlagen sich ändern.
  * Bilder der Mitarbeiter (/uploads/…) wandern in den uploads/-Ordner dieser
    Installation; wo CONSTRUCT ein mitgeliefertes Gesicht hat, gilt dieses.
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
VORLAGEN = BASE / "server" / "team" / "vorlagen" / "agents.default"


def lesen(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def frontmatter_setzen(text: str, key: str, wert: str) -> str:
    if re.search(rf"^{key}:", text, re.M):
        return re.sub(rf"^{key}:.*$", f"{key}: {wert}", text, count=1, flags=re.M)
    return text.replace("\n---\n", f"\n{key}: {wert}\n---\n", 1)


def paare(text: str) -> dict:
    return dict(p.split("=", 1) for p in (x.strip() for x in text.split(",")) if "=" in p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aus", required=True, help="Ordner der FACTORIA-Installation")
    ap.add_argument("--nach", default=str(BASE / "firma"), help="Ziel (Vorgabe: firma/ hier)")
    ap.add_argument("--chef-aus", default="lumina", help="Wessen Akte zur Geschäftsführung wird")
    ap.add_argument("--umbenennen", default="cody=luna,css-spezialist=elara,qa=miranda,auditor=janus",
                    help="alt=neu, kommagetrennt")
    ap.add_argument("--zusammenlegen", default="chanti=chef,design=elara",
                    help="alt=ziel: nur Gedächtnis und Historie wandern, kommagetrennt")
    ap.add_argument("--weglassen", default="druck",
                    help="Kürzel, die gar nicht übernommen werden, kommagetrennt")
    ap.add_argument("--ausfuehren", action="store_true", help="wirklich kopieren (sonst nur zeigen)")
    ap.add_argument("--ersetzen", action="store_true", help="vorhandene Dateien überschreiben")
    args = ap.parse_args()

    quelle, ziel = Path(args.aus).expanduser().resolve(), Path(args.nach).expanduser().resolve()
    if not (quelle / "agents").is_dir():
        sys.exit(f"!! {quelle}/agents gibt es nicht.")
    chef_quelle = args.chef_aus
    umbenennen = {chef_quelle: "chef", **paare(args.umbenennen)}
    zusammen = paare(args.zusammenlegen)
    weg = {x.strip() for x in args.weglassen.split(",") if x.strip()}
    namen = {**umbenennen, **zusammen}        # alt -> neu, überall, wo ein Kürzel steht
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

    def umbenannt(text: str) -> str:
        for alt, neu in namen.items():
            text = re.sub(rf"(?m)^(reports_to:\s*){re.escape(alt)}\s*$", rf"\g<1>{neu}", text)
            # delegates_to: kommagetrennte Liste — den Namen als ganzes Wort ersetzen
            text = re.sub(rf"(?m)^(delegates_to:.*?)\b{re.escape(alt)}\b", rf"\g<1>{neu}", text)
        for alt in weg:
            # aus der Liste streichen, samt Komma davor oder danach
            text = re.sub(rf"(?m)^(delegates_to:.*?)(,\s*\b{re.escape(alt)}\b|\b{re.escape(alt)}\b,?\s*)",
                          r"\g<1>", text)
        return re.sub(r"(?m)^can_hire:.*\n", "", text)

    # ---- Mitarbeiter
    print("Mitarbeiter")
    uploads_noetig: set[str] = set()
    for d in sorted((quelle / "agents").iterdir()):
        if not (d / "AGENT.md").is_file():
            continue
        slug = d.name
        if slug in weg:
            print(f"  {slug}: wird weggelassen")
            continue
        if slug in zusammen:
            print(f"  {slug}: wird nicht einzeln übernommen (Gedächtnis und Historie gehen an {zusammen[slug]})")
            continue
        ziel_slug = umbenennen.get(slug, slug)
        zd = ziel / "agents" / ziel_slug
        akte = umbenannt(lesen(d / "AGENT.md"))
        akte = frontmatter_setzen(akte, "slug", ziel_slug)
        mit = VORLAGEN / ziel_slug
        if slug == chef_quelle:
            # Wie die Vorlage: kein eigenes Foto, der Name kommt beim Laden aus den
            # Einstellungen (die Geschäftsführung ist der Assistent).
            akte = frontmatter_setzen(akte, "name", "Cody")
            akte = frontmatter_setzen(akte, "avatar", "")
        elif (mit / "AGENT.md").is_file():
            # Name, Gesicht und Rolle der Vorlage (der Charakter passt dazu).
            for feld in ("name", "avatar", "title"):
                w = re.search(rf"^{feld}:\s*(.+)$", lesen(mit / "AGENT.md"), re.M)
                if w:
                    akte = frontmatter_setzen(akte, feld, w.group(1).strip())
        m = re.search(r"^avatar:\s*(/uploads/\S+)", akte, re.M)
        if m:
            uploads_noetig.add(m.group(1))
        schreiben(zd / "AGENT.md", akte)
        if (mit / "SOUL.md").is_file():
            schreiben(zd / "SOUL.md", lesen(mit / "SOUL.md"))
        elif (d / "SOUL.md").is_file():
            kopieren(d / "SOUL.md", zd / "SOUL.md")
        if (d / "VORSTELLUNG.md").is_file():
            kopieren(d / "VORSTELLUNG.md", zd / "VORSTELLUNG.md")

    # ---- Gedächtnis und Historie: jede Akte bekommt ihre eigenen und die der Zusammengelegten
    heute = date.today().strftime("%d.%m.%Y")
    ziele = {umbenennen.get(d.name, d.name) for d in (quelle / "agents").iterdir()
             if (d / "AGENT.md").is_file() and d.name not in zusammen and d.name not in weg}
    for slug_neu in sorted(ziele):
        alle = sorted(d.name for d in (quelle / "agents").iterdir() if (d / "AGENT.md").is_file())
        # Die eigene Akte zuerst, danach die zusammengelegten.
        quellen = sorted((x for x in alle if namen.get(x, x) == slug_neu), key=lambda x: x in zusammen)
        gedaechtnis, historie = [], ""
        hinweise = []
        for alt in quellen:
            g = lesen(quelle / "agents" / alt / "MEMORY.md").rstrip("\n")
            if g:
                gedaechtnis.append(g)
            h = lesen(quelle / "agents" / alt / "HISTORIE.jsonl")
            if h:
                historie += ("\n" if historie and not historie.endswith("\n") else "") + h
            if alt in zusammen:
                hinweise.append(alt)
        if slug_neu == "chef":
            hinweise_text = (f"- {heute}: Die frühere Mitarbeiterin {', '.join(hinweise) or 'Chanti'} gibt es in der "
                             f"Firma nicht mehr. Recherche, Inhalte sammeln und Texte schreiben machst du selbst. "
                             f"Du bist die Geschäftsführung und zugleich der Assistent, mit dem der Nutzer im Chat redet. "
                             f"Namen in diesem Gedächtnis, die auf sie zeigen, sind historisch.")
            gedaechtnis.append(hinweise_text)
        elif hinweise:
            gedaechtnis.append(f"- {heute}: {', '.join(hinweise)} arbeitet nicht mehr einzeln; seine Aufgaben "
                               f"(Entwurf und Gestaltungsvorgaben) gehören jetzt zu deinen. Namen in diesem "
                               f"Gedächtnis, die auf ihn zeigen, sind historisch.")
        zd = ziel / "agents" / slug_neu
        if gedaechtnis:
            schreiben(zd / "MEMORY.md", "\n\n".join(gedaechtnis) + "\n")
        if historie.strip():
            schreiben(zd / "HISTORIE.jsonl", historie)
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
            # Stellen, die auf FACTORIA zeigen und sonst ins Leere liefen.
            text = text.replace("factoria_mcp.py", "team_mcp.py").replace("Cody, er baut Factoria", "Cody, er baut die Firma")
            text = text.replace("Lumina ist die Geschäftsführerin, Chanti die Assistentin.", "Die Geschäftsführung ist die Assistentin.")
            text = re.sub(r"(?m)^\| `einstellen` \|.*\n", "", text)           # das Werkzeug gibt es nicht mehr
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
            t["owner"] = namen[t["owner"]]
        esk = t.get("eskalation")
        if isinstance(esk, dict) and esk.get("an") in namen:
            esk["an"] = namen[esk["an"]]   # sonst ginge die Antwort an eine Akte, die es nicht mehr gibt
        t.pop("einstellung", None)
        if t.get("status") == "wartet_auf_einstellung":
            t["status"] = "wartet_auf_kevin"
        if t.get("status") in ("laeuft", "neu"):
            # Ein Auftrag, der in FACTORIA noch lief, startet hier nicht von allein: seine
            # Sitzung gehörte einer anderen Person. Der Nutzer entscheidet, ob es weitergeht.
            t["status"] = "wartet_auf_kevin"
            t["in_arbeit"] = None
            t["eskalation"] = {"bremse": "neustart", "seit": 0, "an": "chef",
                               "grund": "Dieser Auftrag lief noch, als die Firma aus FACTORIA übernommen wurde.",
                               "frage": "Soll es weitergehen? Dann WEITERMACHEN — oder abbrechen."}
        sessions = t.get("sessions") or {}
        t["sessions"] = {namen.get(k, k): v for k, v in sessions.items()}
        je = (t.get("verbraucht") or {}).get("je_agent")
        if isinstance(je, dict):
            neu: dict = {}
            for k, v in je.items():
                neu[namen.get(k, k)] = neu.get(namen.get(k, k), 0) + v
            t["verbraucht"]["je_agent"] = neu
        schreiben(zd / "ticket.json", json.dumps(t, ensure_ascii=False, indent=1))
        zeilen = []
        for z in lesen(d / "thread.jsonl").splitlines():
            try:
                e = json.loads(z)
            except ValueError:
                continue
            for k in ("von", "an"):
                if e.get(k) in namen:
                    e[k] = namen[e[k]]
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
