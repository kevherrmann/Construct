"""Die Belegschaft — Personalakten lesen, prüfen, schreiben.

Ein Mitarbeiter ist ein ORDNER, keine Zeile in einer Datenbank:

    firma/agents/<slug>/AGENT.md    Metadaten (Frontmatter) — Rolle, Modell, Rechte
    firma/agents/<slug>/SOUL.md     sein Charakter. Wer er IST.
    firma/agents/<slug>/MEMORY.md   was er beim Arbeiten gelernt hat (schreibt er selbst)

Dazu, der ganzen Firma gehörend:

    USER.md                   was die Firma über den Nutzer weiß — ALLE dürfen ergänzen
    PROTOCOL.md               die Bus-Regeln (nur in Aufträgen)

Warum Dateien und kein SQLite: weil man eine festgefahrene Firma im Editor
aufmachen und reparieren können muss. Dieselbe Haltung wie in config.py ("die
Datei lässt sich von Hand bearbeiten") — und deshalb wird hier auch beim LESEN
geprüft, nicht nur beim Schreiben. Ein Tippfehler in einer Akte darf die
Oberfläche nicht zerlegen; er macht die Akte fehlerhaft, mehr nicht.

Das Frontmatter-Format ist das der Skills, bewusst ohne YAML-Abhängigkeit:
Listen sind kommagetrennt, Wahrheitswerte sind ja/nein.

Alles, was zur Firma DIESER Installation gehört, liegt unter firma/ und steht in
.gitignore (ein `git pull` frisst nie die eigene Belegschaft). Die Vorlagen
liegen im Programm (server/team/vorlagen/); eine gleichnamige Datei unter firma/
sticht sie — so lässt sich der Hausstil anpassen, ohne Programmdateien zu ändern.
"""
import hashlib
import os
import re
from datetime import date
from pathlib import Path

from server import config as cfg
from server.team.pfade import FIRMA_DIR, USER_FILE

AGENTS_DIR = FIRMA_DIR / "agents"
# Was Mitarbeiter über den Nutzer lernen (`user_merken`), landet NICHT in USER.md: die
# steht im Persona-Prompt des Assistenten in jedem Chat, bei Telegram und im
# Scheduler. Ein Mitarbeiter mit Web-Zugriff, den eine Webseite zu einem Eintrag
# überredet, würde sonst dort dauerhaft Anweisungen hinterlassen. Die Firma liest
# beides; was der Nutzer für richtig hält, übernimmt er selbst in USER.md.
ERGAENZUNGEN_FILE = FIRMA_DIR / "USER-ergaenzungen.md"
VORLAGEN_DIR = Path(__file__).parent / "vorlagen"
DEFAULTS_DIR = VORLAGEN_DIR / "agents.default"
# USER_FILE: dieselbe USER.md wie die des Assistenten im Chat (eine Person, eine
# Datei) — siehe pfade.py.

# Die Geschäftsführung ist der Assistent selbst: der, mit dem der Nutzer im Chat
# redet (mitgeliefert Cody). Sie nimmt Aufträge an, verteilt sie und fasst zusammen.
# Ihr Name kommt immer aus ⚙ Einstellungen, für den Nutzer wie in der Firma (siehe
# load_agent()). So steht ein eigener Name (etwa der, den der Nutzer seinem Assistenten gibt) in keiner
# mitgelieferten Datei, und niemand sonst bekommt ihn zu sehen. Das Kürzel bleibt fest.
OWNER_SLUG = "chef"


def anzeige(a: dict) -> dict:
    """Die Akte, wie der NUTZER sie sieht: die Geschäftsführung mit Name und Gesicht
    seines Assistenten (wie im Chat). Was an ein Modell geht, nimmt die Akte selbst."""
    if a.get("slug") == OWNER_SLUG:
        bild = (cfg.load_settings().get("avatars") or {}).get("assistant") or "/static/cody.png"
        return {**a, "name": cfg.assistant_name(), "avatar": a.get("avatar") or bild}
    return a


def vorlage(name: str) -> Path:
    """Hausstil, Bus-Regeln & Co.: die Datei der Installation, sonst die mitgelieferte."""
    eigene = FIRMA_DIR / name
    return eigene if eigene.exists() else VORLAGEN_DIR / name


def anrede(text: str) -> str:
    """Setzt den Namen des Nutzers in Texte, die an Modelle gehen.

    Die mitgelieferten Regeln sind in Kevins Firma entstanden und sprechen ihn
    mit Namen an. Hier, an der einen Stelle, vor der sie in einen Prompt gehen,
    wird daraus der Name der Installation; bei Kevin selbst bleibt alles wie es
    ist. Das interne Kürzel `kevin` (Absender im Verlauf) bleibt unberührt —
    es ist klein geschrieben und kein Text.
    """
    name = cfg.user_name() or "Nutzer"
    if name == "Kevin":
        return text
    return re.sub(r"Kevin(s?)", lambda m: name + m.group(1), text)

MAX_SOUL = 32_000
MAX_MEMORY = 8_000        # gedeckelt: das Ding hängt an JEDEM Systemprompt
MAX_HISTORIE = 25         # so viele Aufträge bleiben in der Akte
MAX_USER = 32_000
MAX_VORLAGE = 16_000      # PROTOCOL.md ist knapp 9 000 Zeichen; mit 8 000 fehlte sein Ende in jedem Prompt

# Vorerst laeuft alles ueber Claude. Das Feld bleibt, damit spaeter eine zweite
# Maschine dazukann, ohne das Format zu brechen.
ENGINES = ("claude",)
MODELS = ("fable", "opus", "sonnet", "haiku")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Nur die drei, die in einer Firma einen Sinn ergeben. Gemessen mit `claude -p`
# (Modell haiku, Datei schreiben lassen), einmal mit und einmal ohne Write in
# der Werkzeugliste:
#
#   Modus              in der Liste   NICHT in der Liste
#   acceptEdits        schreibt       schreibt (Dateiaenderungen gehen immer)
#   bypassPermissions  schreibt       schreibt (alles geht)
#   auto               schreibt       verweigert
#   dontAsk            schreibt       verweigert   -> dasselbe wie auto
#   default            schreibt       verweigert   -> dasselbe wie auto
#   plan               VERWEIGERT     verweigert   -> kann gar nichts liefern
#
# Raus sind deshalb: plan (ein Mitarbeiter, der nie liefern kann) sowie default
# und dontAsk (verhalten sich wie auto, drei Namen fuer eine Sache).
#
# WICHTIG und ueberraschend: acceptEdits erlaubt Dateiaenderungen AUCH DANN,
# wenn Write und Edit gar nicht in der Werkzeugliste stehen. Wer wirklich
# niemanden schreiben lassen will — einen Pruefer etwa — braucht deshalb `auto`
# UND eine Liste ohne Write/Edit. Die Liste allein reicht nicht.
PERM_MODES = ("acceptEdits", "auto", "bypassPermissions")
STATES = ("active", "paused", "fired")

# Werkzeuge, die eine Akte vergeben darf. Bewusst eine Erlaubnisliste: wer hier
# nicht steht, bekommt es nicht. Bash fehlt mit Absicht NICHT — aber es soll
# eine bewusste Entscheidung pro Rolle sein, keine Vorgabe.
KNOWN_TOOLS = ("Read", "Write", "Edit", "Bash", "Grep", "Glob", "WebSearch",
               "WebFetch", "NotebookEdit", "Task", "TodoWrite", "Skill")

SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
RGB_RE = re.compile(r"^\d{1,3},\d{1,3},\d{1,3}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Farben fuer neue Mitarbeiter. Als r,g,b-Tripel, weil die Oberflaeche sie
# direkt in --accent-rgb kippt und damit ohne EINE Zeile neues CSS auskommt.
PALETTE = ("77,184,255", "255,182,72", "126,231,135", "196,141,255",
           "255,124,124", "104,222,214", "255,158,205", "180,196,120")

DEFAULT_AGENT = {
    "slug": "", "name": "", "title": "", "reports_to": "",
    "engine": "claude", "model": "sonnet", "effort": "high",
    "model_grund": "", "permission_mode": "acceptEdits", "cwd": "",
    "allowed_tools": ["Read", "Grep", "Glob"],
    "can_delegate": False, "delegates_to": [],
    "color": "", "avatar": "", "status": "active",
    "hired": "", "hired_by": "kevin",
    # KEINE Obergrenze fuer Dauer oder Geld eines Zuges: ein Auftrag wie "bau
    # das Projekt" arbeitet stundenlang und ist die ganze Zeit fleissig. Was
    # hier steht, ist eine Haenger-Erkennung — so lange darf ein Zug KEIN
    # Lebenszeichen geben, bevor er als tot gilt.
    "max_stille_s": 1800,
}
_BOOL_FIELDS = ("can_delegate",)


# ---------- Frontmatter ----------
def _split_frontmatter(txt: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", txt, re.S)
    return (m.group(1), m.group(2)) if m else ("", txt)


def _fm_get(fm: str, key: str) -> str:
    # [ \t]* statt \s*: \s schliesst \n ein und wuerde mit re.M ueber ein
    # leeres Feld hinweg die NAECHSTE Zeile als Wert einsammeln.
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", fm, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def _as_bool(v, fallback: bool) -> bool:
    s = str(v).strip().lower()
    if s in ("true", "ja", "yes", "1"):
        return True
    if s in ("false", "nein", "no", "0"):
        return False
    return fallback


def _as_list(v) -> list:
    """Kommagetrennter Text ODER eine fertige Liste.

    Beim Teil-Update kommen die Werte aus einer bereits gelesenen Akte zurueck
    und sind dann echte Listen. Ohne diesen Zweig wuerde str() daraus
    "['Read', 'Write']" machen, und die Anfuehrungszeichen liessen jedes
    Werkzeug durch die Erlaubnisliste fallen.
    """
    if isinstance(v, (list, tuple)):
        items = [str(x) for x in v]
    else:
        items = str(v).replace("[", "").replace("]", "").split(",")
    return [x.strip().strip("\"'") for x in items if x.strip().strip("\"'")]


# ---------- Pruefung ----------
def _color_for(slug: str) -> str:
    """Immer dieselbe Farbe fuer denselben Slug — sonst springt das Organigramm
    bei jedem Neuladen um."""
    h = int(hashlib.sha1(slug.encode()).hexdigest()[:8], 16)
    return PALETTE[h % len(PALETTE)]


def _clean_cwd(v: str, workspace) -> str:
    """Ein Arbeitsverzeichnis ausserhalb des Workspace ist die gefaehrlichste
    Angabe in einer Akte — ein Agent mit Schreibrechten wuerde dort arbeiten.

    workspace kommt aus app.py als str, aus Tests als Path. Die Umwandlung
    steht bewusst VOR dem try: ein Typfehler soll krachen und nicht als
    "Pfad ungueltig" durchgereicht werden — genau das hat hier schon einmal
    einen harmlosen Pfad als Verstoss gemeldet.
    """
    ws = Path(workspace).expanduser().resolve()
    v = str(v or "").strip()
    if not v:
        return str(ws)
    try:
        p = Path(v).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return ""
    if p == ws or str(p).startswith(str(ws) + os.sep):
        return str(p)
    return ""      # leer = ungueltig, wird als Fehler gemeldet


def validate(raw: dict, workspace) -> tuple:
    """Prueft eine Akte und gibt (bereinigt, [Maengel]) zurueck.

    Maengel sind KEINE Ausnahmen: die Akte bleibt lesbar und wird in der
    Oberflaeche als fehlerhaft markiert. Nur so bleibt eine von Hand
    verkorkste Datei reparierbar, statt die Firma unbedienbar zu machen.
    """
    a = dict(DEFAULT_AGENT)
    a["allowed_tools"] = list(DEFAULT_AGENT["allowed_tools"])
    a["delegates_to"] = []
    bad = []

    slug = str(raw.get("slug") or "").strip()
    if not SLUG_RE.match(slug):
        bad.append(f"slug '{slug}' ist unbrauchbar (a-z, 0-9, _-, 2-32 Zeichen)")
        # Nie den rohen Wert behalten: er wird spaeter als Ordnername benutzt,
        # und "../x" waere ein Pfad ausserhalb von agents/.
        slug = re.sub(r"[^a-z0-9_-]", "", slug.lower())[:32] or "unbenannt"
        if not SLUG_RE.match(slug):
            slug = "unbenannt"
    a["slug"] = slug

    a["name"] = (str(raw.get("name") or "").strip() or slug.capitalize())[:40]
    a["title"] = str(raw.get("title") or "").strip()[:60]
    a["reports_to"] = str(raw.get("reports_to") or "").strip()[:32]

    for key, allowed in (("engine", ENGINES), ("model", MODELS),
                         ("effort", EFFORTS), ("permission_mode", PERM_MODES),
                         ("status", STATES)):
        v = str(raw.get(key) or "").strip()
        if v in allowed:
            a[key] = v
        elif v:
            bad.append(f"{key}='{v}' ist nicht erlaubt (moeglich: {', '.join(allowed)})")

    a["model_grund"] = str(raw.get("model_grund") or "").strip()[:200]

    cwd = _clean_cwd(raw.get("cwd"), workspace)
    cwd_ok = bool(cwd)
    if not cwd_ok:
        bad.append(f"cwd '{raw.get('cwd')}' liegt ausserhalb von {Path(workspace)}")
        cwd = str(workspace)
    a["cwd"] = cwd

    # None = Feld fehlt -> Vorgabe. [] = ausdruecklich KEINE Werkzeuge; wer einer
    # Akte alles entzieht, soll nicht still Read/Grep/Glob zurueckbekommen.
    tools = _as_list(raw.get("allowed_tools", "")) if raw.get("allowed_tools") is not None else None
    if tools is not None:
        unknown = [t for t in tools if t not in KNOWN_TOOLS]
        if unknown:
            bad.append(f"unbekannte Werkzeuge: {', '.join(unknown)}")
        a["allowed_tools"] = [t for t in tools if t in KNOWN_TOOLS]
    a["delegates_to"] = [s for s in _as_list(raw.get("delegates_to", "")) if SLUG_RE.match(s)]

    for f in _BOOL_FIELDS:
        a[f] = _as_bool(raw.get(f), DEFAULT_AGENT[f])

    col = str(raw.get("color") or "").strip()
    if RGB_RE.match(col) and all(0 <= int(x) <= 255 for x in col.split(",")):
        a["color"] = col
    else:
        if col:
            bad.append(f"color '{col}' ist kein r,g,b-Tripel")
        a["color"] = _color_for(slug)

    av = str(raw.get("avatar") or "").strip()
    # /uploads/: vom Nutzer hochgeladen; /static/team/: die mitgelieferten Gesichter.
    a["avatar"] = av if (av.startswith(("/uploads/", "/static/team/")) and ".." not in av) else ""

    h = str(raw.get("hired") or "").strip()
    a["hired"] = h if DATE_RE.match(h) else date.today().isoformat()
    a["hired_by"] = str(raw.get("hired_by") or "kevin").strip()[:40]

    try:
        # Untergrenze 300 s: ein einzelner Werkzeugaufruf (Bash, langer Build)
        # darf ohne Zwischenmeldung dauern, ohne dass der Zug abgeschossen wird.
        a["max_stille_s"] = max(300, min(21600, int(float(raw.get("max_stille_s") or 1800))))
    except Exception:
        pass

    # Die eine wirklich gefaehrliche Kombination: ein Agent, der ohne Rueckfrage
    # schreiben darf, und ein Arbeitsverzeichnis, das nicht stimmt.
    #
    # cwd_ok ist hier entscheidend und nicht a["cwd"]: bei ungueltiger Angabe
    # steht in a["cwd"] laengst der Workspace, die Pruefung wuerde also gegen
    # den korrigierten Wert laufen und durchgehen. Wer "/etc" in die Akte
    # schreibt, soll aber NICHT stillschweigend mit vollen Rechten im Workspace
    # landen — er hat sich offensichtlich etwas anderes gedacht.
    if a["permission_mode"] == "bypassPermissions" and not cwd_ok:
        bad.append("bypassPermissions abgelehnt: das cwd war ungueltig")
        a["permission_mode"] = "acceptEdits"
    return a, bad


# ---------- Lesen ----------
def _seed_from_defaults():
    """Beim ersten Start die mitgelieferten Akten anlegen — wie SOUL.default.md
    in config.persona_read()."""
    if AGENTS_DIR.exists() and any(AGENTS_DIR.glob("*/AGENT.md")):
        return
    if not DEFAULTS_DIR.exists():
        return
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    for quelle in sorted(DEFAULTS_DIR.glob("*/")):
        dst = AGENTS_DIR / quelle.name
        dst.mkdir(exist_ok=True)
        for f in quelle.glob("*.md"):
            tgt = dst / f.name
            if not tgt.exists():
                tgt.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")


def load_agent(slug: str, workspace) -> dict | None:
    if not SLUG_RE.match(slug or ""):
        return None
    d = AGENTS_DIR / slug
    f = d / "AGENT.md"
    if not f.exists():
        # Erststart (oder jemand hat agents/ geloescht): Vorlagen ausrollen.
        # Das gehoert hierher und nicht nur in list_agents — sonst antwortet
        # ein direkter Abruf mit 404, obwohl die Akte mitgeliefert wird.
        _seed_from_defaults()
        if not f.exists():
            return None
    try:
        fm, _body = _split_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return {**DEFAULT_AGENT, "slug": slug, "name": slug, "problems": [f"nicht lesbar: {e}"]}
    raw = {k: _fm_get(fm, k) for k in DEFAULT_AGENT}
    raw["slug"] = raw.get("slug") or slug
    if not re.search(r"^allowed_tools:", fm, re.M):
        raw["allowed_tools"] = None      # Zeile fehlt ganz -> Vorgabe, nicht "keine"
    a, bad = validate(raw, workspace)
    a["problems"] = bad
    if slug == OWNER_SLUG:
        # Die Geschäftsführung heißt wie der Assistent, auch für die Kollegen. Der
        # Name in der Akte bleibt, wie er ist (beim Speichern wird er zurückgeschrieben).
        a["name_akte"] = a["name"]
        a["name"] = cfg.assistant_name()
    a["soul"] = _read_capped(d / "SOUL.md", MAX_SOUL)
    a["memory"] = _read_capped(d / "MEMORY.md", MAX_MEMORY)
    a["historie"] = historie_lesen(slug)
    return a


# ---------- Woran jemand schon gearbeitet hat ----------
# Kevins Absicht: dieselbe Art Aufgabe soll immer wieder an dieselbe Person
# gehen, damit sie darin Profi wird. Dafuer muss sie wissen, was sie schon
# gemacht hat — und Luna muss es sehen, um richtig zu verteilen.
#
# Getrennt von MEMORY.md, weil es zwei verschiedene Dinge sind: die Historie
# ist ein Protokoll (schreibt das System), das Gedaechtnis sind Erkenntnisse
# (schreibt der Agent selbst).
def historie_lesen(slug: str) -> list:
    p = AGENTS_DIR / slug / "HISTORIE.jsonl"
    if not p.exists():
        return []
    out = []
    for zeile in p.read_text(encoding="utf-8", errors="replace").splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            out.append(__import__("json").loads(zeile))
        except ValueError:
            continue
    return out[-MAX_HISTORIE:]


def historie_eintragen(slug: str, titel: str, rolle: str, dateien=None):
    """Eine Zeile pro erledigtem Auftrag. Anhaengend, wie der Auftragsverlauf."""
    import json as _json
    d = AGENTS_DIR / slug
    if not (d / "AGENT.md").exists():
        return
    d.mkdir(parents=True, exist_ok=True)
    with (d / "HISTORIE.jsonl").open("a", encoding="utf-8") as f:
        f.write(_json.dumps({"datum": date.today().isoformat(),
                             "titel": str(titel)[:120], "rolle": rolle,
                             "dateien": [str(x)[:200] for x in (dateien or [])][:8]},
                            ensure_ascii=False) + "\n")


def historie_text(slug: str) -> str:
    """Fuer den Systemprompt — knapp, sonst frisst es den Zwischenspeicher."""
    h = historie_lesen(slug)
    if not h:
        return ""
    zeilen = [f"- {e['datum']}: {e['titel']}" + (f" ({e['rolle']})" if e.get("rolle") else "")
              for e in h]
    return "## Woran du schon gearbeitet hast\n\n" + "\n".join(zeilen)


def _read_capped(p: Path, cap: int) -> str:
    """Liest gedeckelt — und sagt Bescheid, wenn wirklich abgeschnitten wurde.

    Das Abschneiden war vorher lautlos. Als HAUSSTIL.md ueber die Grenze wuchs,
    fielen die letzten zwei Abschnitte aus JEDEM Systemprompt heraus, ohne dass
    es irgendwo auffiel — die Regeln standen in der Datei und galten trotzdem
    nicht. Genau die Sorte Fehler, die man ein halbes Jahr lang nicht findet.
    """
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(txt) > cap:
        print(f"[firma] {p.name} ist {len(txt)} Zeichen lang, erlaubt sind {cap} — "
              f"der Rest fehlt im Systemprompt!", flush=True)
    return txt[:cap]


def list_agents(workspace, include_fired=False) -> list:
    _seed_from_defaults()
    out = []
    if AGENTS_DIR.exists():
        for d in sorted(AGENTS_DIR.iterdir()):
            if not (d / "AGENT.md").exists():
                continue
            a = load_agent(d.name, workspace)
            if a and (include_fired or a["status"] != "fired"):
                out.append(a)
    # Die Geschaeftsfuehrung zuerst, danach nach Titel — sonst haengt die
    # Reihenfolge am Zufall des Dateisystems.
    out.sort(key=lambda x: (bool(x["reports_to"]), x["name"].lower()))
    return out


def faehigkeiten(a: dict) -> str:
    """Was ein Mitarbeiter mit seinen Werkzeugen wirklich KANN — als kurzer Text
    fuer die Belegschaftsliste.

    Warum das gebraucht wird: am 11.09.2026 vergab die Geschäftsführung
    Projekt-Screenshots an eine Mitarbeiterin ohne Bash; jeder Browser- oder
    curl-Aufruf wurde mit "requires approval" abgewiesen, und in einer
    `claude -p`-Sitzung im Hintergrund gibt es niemanden, der freigibt. Sie
    eskalierte an den Nutzer, der Auftrag stand. Die Geschäftsführung konnte das
    nicht wissen: die Liste zeigte nur Slug, Name und Titel. Jetzt steht dabei,
    wer eine Shell hat.
    """
    tools = set(a.get("allowed_tools") or ())
    kann = []
    if "Bash" in tools:
        kann.append("Shell (bauen, testen, Browser-Screenshots)")
    # acceptEdits schreibt auch ohne Write/Edit in der Liste (s. PERM_MODES).
    if {"Write", "Edit"} & tools or a.get("permission_mode") in ("acceptEdits", "bypassPermissions"):
        kann.append("schreibt Dateien")
    else:
        kann.append("liest nur")
    if {"WebFetch", "WebSearch"} & tools:
        kann.append("Web")
    return ", ".join(kann)


def org_tree(workspace) -> dict:
    """Baum aus reports_to. Zyklen werden gekappt statt zu haengen — eine
    Akte, die im Kreis zeigt, ist ein Tippfehler, kein Weltuntergang."""
    agents = {a["slug"]: a for a in list_agents(workspace)}
    kids, roots, seen_cycle = {}, [], []
    for slug, a in agents.items():
        boss = a["reports_to"]
        # Kette nach oben verfolgen: landet sie wieder bei uns, ist es ein Zyklus.
        chain, cur = set(), boss
        while cur and cur in agents and cur not in chain:
            chain.add(cur)
            cur = agents[cur]["reports_to"]
        if boss and boss in agents and slug not in chain and boss != slug:
            kids.setdefault(boss, []).append(slug)
        else:
            if boss:
                seen_cycle.append(slug)
            roots.append(slug)

    def node(slug):
        a = anzeige(agents[slug])
        return {"slug": slug, "name": a["name"], "title": a["title"],
                "color": a["color"], "model": a["model"], "effort": a["effort"],
                "status": a["status"], "problems": a["problems"],
                "reports": [node(k) for k in sorted(kids.get(slug, []))]}
    return {"roots": [node(r) for r in sorted(roots)], "cycles": seen_cycle}


# ---------- Schreiben ----------
def _atomic(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


def to_frontmatter(a: dict) -> str:
    def val(k):
        v = a[k]
        if isinstance(v, bool):
            return "ja" if v else "nein"
        if isinstance(v, list):
            return ", ".join(v)
        return str(v)
    keys = [k for k in DEFAULT_AGENT if k != "slug"]
    lines = [f"slug: {a['slug']}"] + [f"{k}: {val(k)}" for k in keys]
    return "---\n" + "\n".join(lines) + "\n---\n"


def _alter_name_haengt_nach(alt: str, slug: str) -> list:
    """Nach einer Umbenennung: wo steht der alte Name noch?

    Angesprochen werden Kollegen ueber den SLUG, der bleibt — ein neuer Name
    bricht also nichts. Aber in den Charakteren steht "du ergaenzt Cody", und in
    der gemeinsamen USER.md stehen Erkenntnisse mit Namen. Das wird nach einer
    Umbenennung still falsch, und niemand merkt es. Also nachsehen und sagen.
    """
    treffer = []
    for d in sorted(AGENTS_DIR.iterdir()) if AGENTS_DIR.exists() else []:
        if d.name == slug:
            continue
        f = d / "SOUL.md"
        if f.exists() and alt in f.read_text(encoding="utf-8", errors="replace"):
            treffer.append(f"firma/agents/{d.name}/SOUL.md")
    if USER_FILE.exists() and alt in USER_FILE.read_text(encoding="utf-8", errors="replace"):
        treffer.append("USER.md")
    if not treffer:
        return []
    return [f"„{alt}“ steht noch in: {', '.join(treffer)} — angesprochen wird zwar "
            f"ueber das Kuerzel „{slug}“, aber die Texte stimmen nicht mehr"]


def save_agent(data: dict, workspace) -> tuple:
    """Teil-Update: was nicht mitkommt, bleibt wie es war.

    Ohne das Zusammenfuehren verliert jedes Speichern aus der Oberflaeche alle
    Felder, die das Formular nicht kennt — die Farbe eines Mitarbeiters sprang
    so beim ersten Bearbeiten auf einen anderen Palettenwert um. Gleiche
    Haltung wie config.apply_patch().
    """
    slug = str(data.get("slug") or "").strip()
    if not SLUG_RE.match(slug):
        # Nichts anlegen, was load_agent nie wieder lesen koennte (und erst
        # recht nichts ausserhalb von agents/).
        return None, [f"slug '{slug}' ist unbrauchbar (a-z, 0-9, _-, 2-32 Zeichen)"]
    vorhanden = load_agent(slug, workspace)
    if vorhanden:
        merged = {k: vorhanden.get(k, v) for k, v in DEFAULT_AGENT.items()}
        merged.update({k: v for k, v in data.items() if v is not None})
        data = merged
        if slug == OWNER_SLUG:
            data["name"] = vorhanden["name_akte"]  # nie den Namen des Assistenten in die Akte
    a, bad = validate(data, workspace)
    alt = (vorhanden or {}).get("name_akte") or (vorhanden or {}).get("name")
    if alt and alt != a["name"]:
        bad += _alter_name_haengt_nach(alt, a["slug"])
    d = AGENTS_DIR / a["slug"]
    _atomic(d / "AGENT.md", to_frontmatter(a))
    if "soul" in data:
        _atomic(d / "SOUL.md", str(data["soul"] or "")[:MAX_SOUL])
    elif not (d / "SOUL.md").exists():
        _atomic(d / "SOUL.md", f"Du bist {a['name']}, {a['title']}.\n")
    if "memory" in data:
        _atomic(d / "MEMORY.md", str(data["memory"] or "")[:MAX_MEMORY])
    return load_agent(a["slug"], workspace), bad


def fire_agent(slug: str, workspace) -> bool:
    """Entlassen heisst status=fired, nicht loeschen. Alte Auftraege sollen
    lesbar bleiben — auch die von Leuten, die nicht mehr da sind."""
    a = load_agent(slug, workspace)
    if not a:
        return False
    a["status"] = "fired"
    _atomic(AGENTS_DIR / slug / "AGENT.md", to_frontmatter(a))
    return True


# ---------- Die geteilte USER.md ----------
# Alle Mitarbeiter duerfen ergaenzen, niemand darf ersetzen. Ein Agent, der die
# Datei "aufraeumt", wuerde die Erkenntnisse der anderen wegwerfen — deshalb
# gibt es hier nur Anhaengen, und zwar mit Herkunftsvermerk, damit man bei
# Widerspruechen sieht, wer was behauptet hat.
_USER_HEADER = """# USER.md — über den Nutzer

Diese Datei gehört dem Assistenten und allen Mitarbeitern der Firma. Jeder darf
ergänzen (Werkzeug `user_merken`), niemand darf löschen oder umschreiben — das
macht der Nutzer selbst. Jede Zeile trägt, von wem sie stammt.
"""
# Die Datei ist auch die USER.md des Assistenten im Chat: sie steht im ⚙-Editor und
# in seinem Systemprompt, also in der Sprache der Installation.
_USER_HEADER_EN = """# USER.md — about the user

This file belongs to the assistant and every employee of the company. Anyone may
add to it (tool `user_merken`), nobody may delete or rewrite — that is the user's
job. Every line says who wrote it.
"""


def user_read() -> str:
    """Was die Firma über den Nutzer weiß: seine USER.md, dahinter die Ergänzungen der
    Mitarbeiter (mit Herkunft)."""
    if not USER_FILE.exists():
        _atomic(USER_FILE, cfg.L(_USER_HEADER, _USER_HEADER_EN))
    haupt = _read_capped(USER_FILE, MAX_USER)
    zusatz = _read_capped(ERGAENZUNGEN_FILE, MAX_USER) if ERGAENZUNGEN_FILE.exists() else ""
    if zusatz.strip():
        haupt = haupt.rstrip("\n") + "\n\n## Von Mitarbeitern ergänzt\n\n" + zusatz.strip() + "\n"
    return haupt


def ergaenzungen_read() -> str:
    return _read_capped(ERGAENZUNGEN_FILE, MAX_USER) if ERGAENZUNGEN_FILE.exists() else ""


def user_append(fact: str, by: str) -> tuple:
    """Eine Zeile anhaengen — an die Ergänzungen, nicht an USER.md. Gibt (ok, Meldung)
    zurueck.

    Der Aufrufer muss die Sperre halten (siehe bus.py) — hier steht nur die
    Datei-Arbeit, damit die Funktion auch ohne laufende Ereignisschleife
    testbar bleibt.
    """
    fact = " ".join(str(fact or "").split())[:400]
    if not fact:
        return False, "leerer Eintrag"
    cur = user_read()
    if fact.lower() in cur.lower():
        return False, "steht schon drin"
    zusatz = ergaenzungen_read()
    if len(cur) + len(fact) + 60 > MAX_USER:
        return False, ("Die Datei über den Nutzer ist voll (%d Zeichen). Der Nutzer muss aufräumen — "
                       "ich kürze nicht selbst." % len(cur))
    line = f"- {fact}  <!-- {by}, {date.today().isoformat()} -->\n"
    _atomic(ERGAENZUNGEN_FILE, zusatz.rstrip("\n") + ("\n" if zusatz.strip() else "") + line)
    return True, "gemerkt"


def style_read() -> str:
    """Der Hausstil — gilt IMMER. Getrennt von PROTOCOL.md, das nur die
    Bus-Regeln der Auftragsarbeit enthaelt."""
    return _vorlage_lesen("HAUSSTIL.md")


def protocol_read() -> str:
    return _vorlage_lesen("PROTOCOL.md")


def gestaltung_read() -> str:
    """Was in dieser Firma "gut aussehen" heisst.

    Eigene Datei statt eines Abschnitts im Hausstil: Gestaltung braucht Platz,
    und der Hausstil gilt auch am Telefon. Haengt in Auftraegen an jedem
    Systemprompt — auch am dem von jemandem, der erst naechstes Jahr
    eingestellt wird.
    """
    return _vorlage_lesen("GESTALTUNG.md")


def _vorlage_lesen(name: str) -> str:
    p = vorlage(name)
    return _read_capped(p, MAX_VORLAGE) if p.exists() else ""
