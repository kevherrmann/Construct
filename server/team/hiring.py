"""Das Einstellungsverfahren — ein Vorschlag, Kevin entscheidet.

Fehlt eine Rolle, schlaegt die Geschaeftsfuehrung EINEN Kandidaten vor, und
Kevin stellt ein, benennt um oder lehnt ab. Nicht: die Firma stellt selbst ein.

Frueher waren es drei zur Auswahl — "einer gruendlich, einer schnell, einer
Spezialist". Das war als Kontrolle gedacht und war in Wahrheit Theater: wer
jemanden einstellt, weil ihm eine Faehigkeit fehlt, will dafuer den Besten und
nicht den Zweitbesten daneben. Kevins echtes Interesse an der Auswahl war der
NAME — und den kann er am Vorschlag direkt aendern.

Die Erzeugung ist bewusst KEIN Gespraechszug, sondern ein einzelner kurzer
Aufruf ohne Werkzeuge und ohne Bus (~5 s, gut zehn Cent). `--json-schema`
erzwingt die Struktur, sodass kein Text geparst werden muss.

Wichtig am Prompt: KEIN Kompromissprofil. Ohne diese Auflage bekommt man einen
Alleskoenner, der nichts von dem besonders kann, wofuer er eingestellt wird.
"""
import json
import subprocess

from server.team import agents as ag

RUNDEN_MAX = 2      # so oft darf Kevin neue Vorschlaege anfordern

SCHEMA = {
    "type": "object", "required": ["kandidaten"], "additionalProperties": False,
    "properties": {"kandidaten": {
        "type": "array", "minItems": 1, "maxItems": 1,
        "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "titel", "slug", "kurz", "staerken", "arbeitsweise",
                         "model", "effort", "model_grund", "permission_mode",
                         "allowed_tools", "can_delegate", "systemprompt"],
            "properties": {
                "name": {"type": "string", "description": "Vorname, deutsch, kurz"},
                "titel": {"type": "string", "description": "Rolle, z.B. Frontend-Entwicklerin"},
                "slug": {"type": "string",
                         "description": "kurzes Kuerzel der ROLLE, klein, a-z0-9-, "
                                        "z.B. frontend oder qa — NICHT der Name"},
                "kurz": {"type": "string", "description": "ein bis zwei Saetze"},
                "staerken": {"type": "array", "minItems": 3, "maxItems": 3,
                             "items": {"type": "string"}},
                "arbeitsweise": {"type": "string", "description": "ein Satz"},
                "model": {"type": "string", "enum": list(ag.MODELS)},
                "effort": {"type": "string", "enum": list(ag.EFFORTS)},
                "model_grund": {"type": "string", "description": "ein Satz Begruendung"},
                "permission_mode": {"type": "string", "enum": ["acceptEdits", "auto"]},
                "allowed_tools": {"type": "array", "items": {
                    "type": "string", "enum": list(ag.KNOWN_TOOLS)}},
                "can_delegate": {"type": "boolean"},
                "systemprompt": {"type": "string",
                                 "description": "Der spaetere Charakter dieser Person. "
                                                "Deutsch, per du, 10-25 Zeilen."},
            }}}}}


def _prompt(rolle: str, warum: str, brief: str, roster: list, hinweis: str) -> str:
    belegschaft = "\n".join(
        f"- {a['slug']}: {a['name']}, {a['title']} ({a['model']}/{a['effort']})"
        for a in roster) or "(noch niemand)"
    leitfaden = ag._read_capped(ag.vorlage("MODELS.md"), 6000)
    stil = ag.style_read()
    p = [
        # Kennzeile: dieser Lauf gehoert der Firma, nicht dem Nutzer. Das
        # Einstellungsverfahren laeuft ohne Bus und waere in der Sitzungsliste
        # sonst nicht von einem Gespraech zu unterscheiden (INTERN_MARKEN in
        # server/sessions.py).
        "[firma-intern]",
        "Du besetzt eine Stelle in einer kleinen Firma aus KI-Mitarbeitern.",
        f"## Gesuchte Rolle\n{rolle}",
        f"## Warum sie gebraucht wird\n{warum}",
    ]
    if brief:
        p.append(f"## Der Auftrag, bei dem es aufgefallen ist\n{brief}")
    p += [
        f"## Wer schon hier arbeitet\n{belegschaft}",
        "Die Vorschlaege sollen die Belegschaft ERGAENZEN, nicht doppeln.",
        f"## Leitfaden fuer Modell und Effort\n{leitfaden}",
        f"## Hausstil, an den sich alle halten\n{stil}",
        "## Deine Aufgabe",
        "Schlage GENAU EINEN Kandidaten vor: den bestmoeglichen Spezialisten fuer "
        "genau diesen Fall. Kein Kompromissprofil, kein Alleskoenner, keine zweite "
        "Meinung — die Firma stellt jemanden ein, WEIL ihr eine bestimmte Faehigkeit "
        "fehlt, und dann will Kevin dafuer den Besten. Es gibt hier nichts zu waehlen, "
        "nur etwas zu treffen.",
        "Der slug benennt die ROLLE (frontend, qa, recherche), nicht den Menschen — "
        "die Kollegen sprechen sich damit an. Er darf keinen der oben genannten "
        "wiederholen.",
        "Waehle Modell und Effort nach dem Leitfaden und begruende es in EINEM Satz. "
        "Gib die Werkzeuge, die die Rolle WIRKLICH BRAUCHT — lieber eins zu viel als "
        "eins zu wenig: wer nichts ausfuehren darf, kann sein Ergebnis auch nicht "
        "pruefen. Wer eine Oberflaeche baut, braucht Bash und Write, sonst kann er "
        "nichts starten und nichts anlegen.",
        # Der Satz hier war frueher "wer sie ist, wie sie arbeitet, was sie NICHT tut".
        # Ergebnis: das Modell fuellte das "was sie nicht tut" mit erfundenen
        # Kollegen ("das machen Nora und Finn") und verbot der Person Werkzeuge,
        # die sie laut Akte hatte. Sie hat sich monatelang daran gehalten.
        "Der systemprompt ist der spaetere Charakter dieser Person: wer sie ist, wie "
        "sie arbeitet, worauf sie besteht. Deutsch, per du, ohne Gendern.",
        "HARTE REGELN fuer den systemprompt:",
        "1. Erfinde NIEMANDEN. Du darfst ausschliesslich Kollegen erwaehnen, die oben "
        "unter 'Wer schon hier arbeitet' stehen. Es gibt sonst niemanden — kein Team, "
        "keine Zuarbeit, keine Abteilung. Wer eine Aufgabe an einen erfundenen Kollegen "
        "abgibt, gibt sie an niemanden ab.",
        "2. Verbiete der Person nichts, was ihre Werkzeugliste erlaubt. Ihre Rolle darf "
        "nicht enger sein als ihre Ausstattung — sonst ruehrt sie Werkzeuge nicht an, "
        "die sie braucht.",
        "3. Grenze die Rolle nach Zustaendigkeit ab, nicht nach Verbot: 'die Datenbank "
        "gehoert Cody, melde ihm Probleme dort' statt 'du machst kein Backend'.",
        "4. Wiederhole NICHT den Hausstil, die Bus-Regeln oder die Gestaltungsregeln — "
        "die haengen ohnehin an jedem Systemprompt. Schreib, wer diese Person ist und "
        "was sie in ihrem Fach besonders gut macht.",
        "5. Sie arbeitet allein und ohne Rueckfragemoeglichkeit. Ihr Charakter muss sie "
        "in die Lage versetzen, eine Aufgabe von Anfang bis Ende selbst zu erledigen "
        "und ihr eigenes Ergebnis zu pruefen.",
    ]
    if hinweis:
        p.append(f"## Kevin war mit den letzten Vorschlaegen unzufrieden\n{hinweis}\n"
                 "Nimm das ernst und schlage etwas deutlich anderes vor.")
    return ag.anrede("\n\n".join(p))


def kandidaten(rolle: str, warum: str, brief: str, roster: list,
               claude_bin: str, env: dict, hinweis: str = "") -> tuple:
    """Gibt (liste, fehler) zurueck. Blockierend — Aufrufer nutzt to_thread."""
    cmd = [claude_bin, "-p", "--output-format", "json",
           "--json-schema", json.dumps(SCHEMA),   # inline, NICHT als Dateipfad
           # Bewusst das starke Modell: dieser eine Aufruf schreibt den Charakter,
           # nach dem ein Mitarbeiter danach JEDEN Zug macht. Zehn Cent gespart
           # und dafuer ein halbes Jahr eine kaputte Rolle ist ein schlechter Tausch.
           "--model", "opus", "--effort", "high",
           "--permission-mode", "plan",           # er soll nur denken, nicht arbeiten
           # Keine Werkzeuge, keine fremden MCP-Server: der Lauf braucht beides
           # nicht, und ohne die Flags laedt claude Kevins persoenliche
           # MCP-Konfiguration mit (siehe build_claude_cmd(intern=True) in server/team/lauf.py).
           "--tools", "", "--strict-mcp-config"]
    try:
        # env NICHT vergessen: darin steckt der Web-Login-Token. Ohne ihn
        # scheitert die Suche auf jeder Installation, die nur per Web-Login
        # angemeldet ist — mit einem Auth-Fehler, der nach allem aussieht.
        r = subprocess.run(cmd, input=_prompt(rolle, warum, brief, roster, hinweis),
                           capture_output=True, text=True, timeout=240, env=env)
    except subprocess.TimeoutExpired:
        return [], "Die Kandidatensuche hat zu lange gebraucht."
    if r.returncode != 0:
        return [], (r.stderr or "").strip()[:300] or f"claude endete mit {r.returncode}"
    try:
        aussen = json.loads(r.stdout)
        # result ist ein STRING mit dem geprueften JSON darin, kein Objekt.
        innen = json.loads(aussen["result"]) if isinstance(aussen.get("result"), str) \
            else aussen.get("result") or {}
    except (ValueError, KeyError, TypeError) as e:
        return [], f"Antwort nicht lesbar: {type(e).__name__}"
    liste = innen.get("kandidaten") or []
    return liste[:3], "" if liste else "keine Kandidaten erhalten"


def als_akte(k: dict, workspace) -> dict:
    """Kandidat -> Personalakte, wie save_agent sie erwartet."""
    return {
        "slug": str(k.get("slug") or "").strip().lower(),
        "name": k.get("name") or "", "title": k.get("titel") or "",
        "reports_to": ag.OWNER_SLUG,
        "engine": "claude", "model": k.get("model") or "sonnet",
        "effort": k.get("effort") or "high", "model_grund": k.get("model_grund") or "",
        "permission_mode": k.get("permission_mode") or "acceptEdits",
        "cwd": str(workspace),
        "allowed_tools": k.get("allowed_tools") or ["Read", "Grep", "Glob"],
        "can_delegate": bool(k.get("can_delegate")), "can_hire": False,
        "status": "active", "hired_by": "kevin",
        "soul": k.get("systemprompt") or "",
    }
