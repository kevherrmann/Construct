#!/usr/bin/env python3
"""Übernimmt alle Dokumente aus Paperless-ngx in die Dokumente-Ablage.

  python3 scripts/dokumente_aus_paperless.py --url http://localhost:8010 --token-datei ~/paperless/api-token
  (ohne --ausfuehren nur anzeigen, was übernommen würde)

Geholt wird je Dokument das durchsuchbare PDF (Paperless' Archivfassung, sonst
das Original) mit Titel, Datum, Absender, Typ, Tags und Notiz. Was in Paperless
noch im Posteingang lag, landet auch hier im Eingang, alles andere gilt als
bestätigt und dient sofort als Lernstoff. Paperless selbst bleibt unangetastet.
"""
import argparse
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.dokumente import ablage  # noqa: E402


def holen(url: str, token: str, roh: bool = False):
    req = urllib.request.Request(url, headers={"Authorization": f"Token {token}",
                                               "Accept": "application/json; version=9"})
    with urllib.request.urlopen(req, timeout=120) as r:
        daten = r.read()
    return daten if roh else json.loads(daten)


def alle(basis: str, token: str, pfad: str) -> list[dict]:
    raus, url = [], f"{basis}{pfad}{'&' if '?' in pfad else '?'}page_size=100"
    while url:
        seite = holen(url, token)
        raus += seite["results"]
        url = seite.get("next")
    return raus


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", required=True)
    p.add_argument("--token", default="")
    p.add_argument("--token-datei", default="")
    p.add_argument("--ausfuehren", action="store_true")
    a = p.parse_args(argv)
    token = a.token or Path(a.token_datei).expanduser().read_text().strip()
    # Selbst lesen, nicht im Hintergrund: der Thread stürbe mit dem Skript
    ablage.HINTERGRUND = False
    basis = a.url.rstrip("/")

    namen = {k: {x["id"]: x["name"] for x in alle(basis, token, f"/api/{k}/")}
             for k in ("correspondents", "document_types", "tags")}
    eingang_tags = {x["id"] for x in alle(basis, token, "/api/tags/") if x.get("is_inbox_tag")}
    docs = alle(basis, token, "/api/documents/?ordering=id")
    print(f"{len(docs)} Dokumente in Paperless")

    for d in docs:
        tags = [namen["tags"][t] for t in d["tags"] if t in namen["tags"] and t not in eingang_tags]
        zeile = (f"#{d['id']} {d['created'][:10]}  {namen['correspondents'].get(d['correspondent'], '?')}  "
                 f"{namen['document_types'].get(d['document_type'], '?')}  {d['title']}  {tags}")
        if not a.ausfuehren:
            print("  " + zeile)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "dok.pdf"
            try:
                pdf.write_bytes(holen(f"{basis}/api/documents/{d['id']}/download/", token, roh=True))
            except OSError as e:
                print(f"  FEHLER {zeile}: {e}")
                continue
            if not pdf.read_bytes().startswith(b"%PDF"):
                print(f"  übersprungen (kein PDF): {zeile}")
                continue
            neu = ablage.neu(pdf, titel=d["title"], quelle="paperless")
        notiz = "\n".join(n.get("note", "") for n in d.get("notes") or [] if n.get("note"))
        ablage.aendern(neu["id"], {
            "datum": d["created"][:10],
            "absender": namen["correspondents"].get(d["correspondent"]),
            "typ": namen["document_types"].get(d["document_type"]),
            "tags": tags,
            "notiz": notiz,
            "eingang": bool(set(d["tags"]) & eingang_tags),
        })
        print(f"  übernommen als #{neu['id']}: {zeile}")

    if a.ausfuehren:
        print("Lese die PDFs ein (Text, Vorschau) …")
        ablage.jetzt_lesen_alle()
        print(f"fertig: {ablage.uebersicht()['gesamt']} Dokumente in der Ablage")
    else:
        print("Nur angezeigt. Mit --ausfuehren übernehmen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
