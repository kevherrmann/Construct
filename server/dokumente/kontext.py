"""Block für den System-Prompt: was in der Ablage liegt und wie der Assistent
damit arbeitet. Nur Zahlen, keine Inhalte: die liest er gezielt nach, wenn
eine Frage es braucht."""
import sys
from pathlib import Path

from server import config as cfg

from . import ablage, sicherung

CLI = Path(__file__).resolve().parent.parent.parent / "doku.py"


def block() -> str:
    if not (ablage.DATEN / "dokumente.db").exists():
        u = {"gesamt": 0, "eingang": 0, "lesen": 0}
    else:
        u = ablage.uebersicht()
    warnung = _sicherung_warnung(u["gesamt"], cfg.lang() == "en")
    # Der Interpreter des Servers, nicht python3 aus dem PATH: doku.py braucht
    # pypdf und Co. aus dem venv, das System-Python hat sie nicht.
    befehl = f'"{sys.executable}" "{CLI}"'
    if cfg.lang() == "en":
        stand = f"{u['gesamt']} documents, {u['eingang']} of them in the inbox (not yet sorted)"
        if u["lesen"]:
            stand += f", {u['lesen']} still being read"
        return (f"## The user's document archive (Documents tile)\n{stand}.\n"
                f"Commands: `{befehl} search \"words\"` · `show ID` · `inbox` · "
                "`set ID --title … --date YYYY-MM-DD --sender … --type … --tags a,b --done` · `split ID \"1-2, 3\"` · `merge ID ID …` · `names`.\n"
                "Sorting the inbox: read each document with show, set title, date, sender, type and "
                "tags, then --done. Reuse existing names (see names) instead of inventing variants.\n"
                "Privacy: whatever you read with show goes to the model provider. Only read the "
                "documents a question actually needs." + warnung)
    stand = f"{u['gesamt']} Dokumente, davon {u['eingang']} im Eingang (noch nicht einsortiert)"
    if u["lesen"]:
        stand += f", {u['lesen']} werden gerade gelesen"
    return (f"## Dokumente-Ablage des Nutzers (Kachel Dokumente)\n{stand}.\n"
            f"Befehle: `{befehl} search \"Wörter\"` · `show ID` · `inbox` · "
            "`set ID --title … --date JJJJ-MM-TT --sender … --type … --tags a,b --done` · `split ID \"1-2, 3\"` · `merge ID ID …` · `names`.\n"
            "Eingang einsortieren: jedes Dokument mit show lesen, Titel, Datum, Absender, Typ und Tags "
            "setzen, dann --done. Vorhandene Namen nehmen (siehe names), keine Varianten erfinden.\n"
            "Datenschutz: Was du mit show liest, geht an den Modellanbieter. Lies nur die Dokumente, "
            "die eine Frage wirklich braucht." + warnung)


def _sicherung_warnung(gesamt: int, en: bool) -> str:
    """Nur wenn etwas nicht stimmt: wer Papier wegwirft, muss sich auf die
    Sicherung verlassen können."""
    if not gesamt:
        return ""
    try:
        s = sicherung.stand()
    except Exception:
        return ""
    if not s["eingerichtet"]:
        return ("\nWARNING: no backup is set up (Documents → Backup). Mention it before the user "
                "throws paper away." if en else
                "\nACHTUNG: Es ist keine Sicherung eingerichtet (Dokumente → Sicherung). Sag das, "
                "bevor der Nutzer Papier wegwirft.")
    kaputt = [z for z, v in s["ziele"].items() if v["an"] and v["fehler"]]
    if kaputt:
        return (f"\nWARNING: backup to {', '.join(kaputt)} failed: "
                f"{s['ziele'][kaputt[0]]['fehler']}" if en else
                f"\nACHTUNG: Sicherung nach {', '.join(kaputt)} fehlgeschlagen: "
                f"{s['ziele'][kaputt[0]]['fehler']}")
    return ""
