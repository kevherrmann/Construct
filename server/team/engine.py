"""Die Firma bei der Arbeit: Dispatcher, Züge, Bremsen, Direktgespräch.

Ein Auftrag ist ein Verlauf von Nachrichten zwischen Mitarbeitern (auftraege.py).
Der Dispatcher stellt sie zu: je Nachricht ein Zug, das ist ein `claude -p`-
Prozess des Empfängers mit dem Firmen-Bus als einzigem MCP-Server (team_mcp.py).
Was ein Mitarbeiter sagen will, geht als Werkzeugaufruf zurück an den Server
(bus.py), der die nächste Nachricht einreiht. Nichts wartet aufeinander: jeder
Aufruf kehrt sofort zurück, der Zug endet, die Antwort kommt als neue Nachricht.

Der Zustand lebt auf der Platte, nicht hier — nur so überlebt ein Auftrag den
Neustart des Servers. Hier im Prozess stehen nur Schlösser, laufende Züge und
die Ereignispuffer für die Oberfläche.

Der Server ist für EINEN uvicorn-Worker gebaut.
"""
import asyncio
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

from server import telegram_bot as tgmod
from server.core import BASE_DIR, WORKSPACE, bus_auth_header, bus_base
from server.team import agents as ag
from server.team import auftraege as auf
from server.team import guards
from server.team.gedaechtnis import CHAT_WERKZEUGE, chat_session_id
from server.team.lauf import build_claude_cmd, spawn
from server.team.prompts import agent_system_prompt, auftrags_prompt, ausstehend


def tg_send(text: str):
    """Meldung aufs Telefon — im Hintergrund, damit der Dispatcher nie darauf wartet."""
    threading.Thread(target=tgmod.send_owner, args=(text,), daemon=True).start()


BUS_NUR_LESEN = ("belegschaft", "notiz", "merken", "user_merken", "antworten", "liefern",
                 "anleitung", "anleitung_anlegen")


def bus_werkzeuge(a: dict) -> list:
    """Welche Bus-Werkzeuge dieser Mitarbeiter bekommt.

    Die Erlaubnisliste ist der echte Hebel — im Rauchtest hat die CLI ein nicht
    aufgefuehrtes Werkzeug sauber verweigert. Wer nicht verteilen darf, bekommt
    `beauftragen` also gar nicht erst in die Hand.
    """
    erlaubt = list(BUS_NUR_LESEN) + ["fragen", "eskalieren", "rechnen", "kontrast"]
    if a.get("can_delegate"):
        erlaubt.append("beauftragen")
    if a.get("can_hire"):
        erlaubt.append("einstellen")
    return [f"mcp__firma__{w}" for w in erlaubt]


def start_agent_turn(a: dict, t: dict, nachricht: dict):
    """Ein Zug in der Auftragsarbeit — mit Bus."""
    d = ag.AGENTS_DIR / a["slug"]
    d.mkdir(parents=True, exist_ok=True)
    spf = d / f".sysprompt-{t['id']}"
    ag._atomic(spf, agent_system_prompt(a, WORKSPACE, auftrag=True))

    token = uuid.uuid4().hex
    BUS_TOKENS[token] = (a["slug"], t["id"])
    mcp = bus_config(a["slug"], token, t["id"])

    cmd = build_claude_cmd(
        mode=a["permission_mode"], model=a["model"], effort=a["effort"],
        session_id=t["sessions"].get(a["slug"]) or None,
        system_prompt_file=spf,
        allowed_tools=list(a["allowed_tools"]) + bus_werkzeuge(a),
        mcp_config=mcp)
    return spawn(cmd, t.get("cwd") or a["cwd"], a["model"],
                  auftrags_prompt(a, t, nachricht),
                  t["sessions"].get(a["slug"]) or None, agent_slug=a["slug"],
                  auftrag_id=t["id"], bus_token=token)


# ---------- Auftraege: der Dispatcher ----------
# Eine Schleife, die Nachrichten zwischen Mitarbeitern zustellt. Sequenziell
# pro Auftrag, hoechstens zwei Zuege gleichzeitig ueber alle Auftraege — jeder
# Zug ist ein voller claude-Prozess (200-400 MB), und die 5h/7d-Fenster des
# Kontos sind real.
#
# Der Zustand lebt auf der Platte (tickets.py), nicht hier: nur so ueberlebt
# ein Auftrag den Neustart des Servers.
# Beide werden hier angelegt und nicht erst in dispatcher_loop: eine
# asyncio.Queue bindet sich erst bei der ersten Benutzung an die Schleife, und
# so gibt es kein Zeitfenster, in dem ein per API angelegter Auftrag im Verlauf
# steht, aber nie zugestellt wird.
MAILBOX = asyncio.Queue()
# Wie viele Zuege gleichzeitig — jeder ist ein voller claude-Prozess. Seit die
# Geschaeftsfuehrung unabhaengige Teile parallel vergeben darf, ist das ein
# echter Hebel; hoeher als 4 stellt niemand, ohne die 5h-Fenster zu kennen.
PARALLEL = max(1, min(4, int(os.environ.get("CONSTRUCT_TEAM_PARALLEL", "2") or 2)))
TURN_SEM = asyncio.Semaphore(PARALLEL)
LIMIT_BIS = 0.0                       # Nutzungslimit gerissen: bis dahin startet kein Zug
LIMIT_GEMELDET = set()                # damit Telegram je Limit nur einmal klingelt
FEEDS = {}                            # ticket_id -> AuftragsFeed
BUS_TOKENS = {}                       # token -> (agent_slug, ticket_id), nur solange der Zug laeuft
PAUSIERT = False                      # grosser roter Knopf
AUFTRAG_LOCKS = {}                     # ticket_id -> asyncio.Lock (Datei-Aenderung)
ZUG_LOCKS = {}                        # ticket_id -> asyncio.Lock (ein Zug nach dem anderen)


def auftrag_lock(tid: str):
    if tid not in AUFTRAG_LOCKS:
        AUFTRAG_LOCKS[tid] = asyncio.Lock()
    return AUFTRAG_LOCKS[tid]


def zug_lock(tid: str):
    """Sequenziell pro Auftrag — das Versprechen aus dem Kommentar oben.

    Ohne diese Sperre laufen zwei Nachrichten desselben Auftrags parallel
    (nach einem Neustart reiht wieder_aufnehmen ALLE offenen ein), und zwei
    `claude --resume` auf dieselbe Sitzung desselben Mitarbeiters zerlegen
    die Sitzung.
    """
    if tid not in ZUG_LOCKS:
        ZUG_LOCKS[tid] = asyncio.Lock()
    return ZUG_LOCKS[tid]


def wartezeit_abziehen(t: dict):
    """Die Zeit, in der der Auftrag auf Kevin gewartet hat, zaehlt nicht als
    Laufzeit. Sonst reisst nach einer Nacht Pause gleich die Zeit-Bremse."""
    seit = ((t.get("eskalation") or {}).get("seit")
            or (t.get("einstellung") or {}).get("seit"))
    if seit:
        t["verbraucht"]["start"] = t["verbraucht"].get("start", time.time()) + (time.time() - seit)


async def auftrag_aendern(tid: str, aendern):
    """Laden, ändern, speichern — als EINE Einheit.

    Ohne das ueberschreiben sich zwei Zuege gegenseitig: der eine laedt den
    Auftrag, der andere setzt inzwischen sein in_arbeit, und der erste schreibt
    seinen veralteten Stand darueber. Beobachtet an einem echten Auftrag —
    in_arbeit stand auf None, obwohl ein Zug lief. Nach einem Neustart haette
    wieder_aufnehmen() die unquittierte Nachricht fuer unerledigt gehalten und
    ERNEUT eingereiht.

    `aendern` bekommt den frisch geladenen Auftrag und darf ihn veraendern;
    gibt es ihn nicht mehr, passiert nichts.
    """
    async with auftrag_lock(tid):
        t = auf.laden(tid)
        if not t:
            return None
        aendern(t)
        auf.speichern(t)
        return t


class AuftragsFeed:
    """Fast dieselbe Mechanik wie class Run, nur auf Auftragsebene.

    Bewusst eine Kopie und keine gemeinsame Basisklasse: Run puffert die
    Ausgabe EINES Prozesses, das hier den Nachrichtenverkehr vieler Zuege.
    Die Gemeinsamkeit ist "Backlog dann live", und die sind vierzig Zeilen —
    eine Abstraktion darueber waere mehr Aufwand als Nutzen.
    """

    def __init__(self, tid):
        self.id = tid
        self.events = []
        self.subs = set()

    def emit(self, ev):
        self.events.append(ev)
        if len(self.events) > 4000:
            del self.events[:1000]
        for q in list(self.subs):
            q.put_nowait(ev)


def feed(tid) -> AuftragsFeed:
    if tid not in FEEDS:
        FEEDS[tid] = AuftragsFeed(tid)
    return FEEDS[tid]


def _sha(pfad: str) -> str:
    try:
        return hashlib.sha1(Path(pfad).read_bytes()).hexdigest()[:12]
    except Exception:
        return ""


def bus_einreihen(t: dict, von: str, an: str, art: str, text: str,
                  tiefe: int = 0, dateien=None, groesse: str = "") -> dict:
    """Eine Nachricht in den Verlauf schreiben und zur Zustellung anmelden."""
    eintrag = {"von": von, "an": an, "art": art, "text": str(text)[:20000],
               "tiefe": tiefe, "dateien": dateien or []}
    if groesse:
        eintrag["groesse"] = groesse
    e = auf.anhaengen(t["id"], eintrag)
    feed(t["id"]).emit({"type": "msg", **e})
    MAILBOX.put_nowait((t["id"], e["id"]))
    return e


def auftrag_anhalten(t: dict, bremse: str, grund: str, frage: str = "", an: str = ""):
    """Jede Bremse endet hier: Auftrag friert ein, Kevin wird geholt.

    Laedt bewusst frisch von der Platte: der Aufrufer haelt den Auftrag
    womoeglich seit Minuten in der Hand, und inzwischen hat ein anderer Zug
    Kosten oder Sitzungen dazugeschrieben.
    """
    frisch = auf.laden(t["id"]) or t
    if frisch["status"] in ("fertig", "abgebrochen"):
        # Ein abgeschlossener Auftrag wird nicht wieder aufgemacht — etwa wenn
        # der Stop-Knopf einen Zug trifft, der laengst geliefert hat.
        print(f"[bremse] {bremse} ignoriert, Auftrag {t['id']} ist {frisch['status']}", flush=True)
        return
    frisch["status"] = "wartet_auf_kevin"
    # "an": wer eskaliert hat — Kevins Antwort geht dann an genau den zurueck,
    # nicht pauschal an die Geschaeftsfuehrung.
    if not frage:
        # Stand hier nur "Wie soll es weitergehen?", wusste Kevin nicht, was
        # von ihm verlangt wird — und suchte in den Nachrichten nach einer
        # Luecke, die er fuellen muss (11.09.2026). Die meisten Bremsen wollen
        # nur ein Hinsehen; das muss dastehen.
        wer = (ag.load_agent(an, WORKSPACE) or {}).get("name") if an else ""
        wer = wer or (ag.load_agent(frisch["owner"], WORKSPACE) or {}).get("name") or "die Geschäftsführung"
        frage = (f"Sieh kurz hin, ob der Auftrag noch auf dem richtigen Weg ist. Dann "
                 f"WEITERMACHEN — ohne Text bekommt {wer} \u201eMach bitte weiter\u201c und die "
                 f"Bremsen zählen von vorn. Willst du etwas ändern, schreib es {wer} in "
                 f"einem Satz; abbrechen geht auch.")
    frisch["eskalation"] = {"bremse": bremse, "grund": grund, "frage": frage,
                            "seit": time.time(), "an": an}
    frisch["in_arbeit"] = None
    auf.speichern(frisch)
    t = frisch
    auf.anhaengen(t["id"], {"art": "system", "bremse": bremse, "text": grund})
    feed(t["id"]).emit({"type": "eskalation", "bremse": bremse, "grund": grund,
                        "frage": t["eskalation"]["frage"]})
    v = t["verbraucht"]
    titel = t["titel"]
    tg_send(f"\u23f8 Auftrag \u201e{titel}\u201c wartet auf dich\n"
            f"{guards.NAMEN.get(bremse, bremse)}: {grund}\n"
            f"Was du tun kannst: {frage}\n"
            f"{v['hops']} Schritte, {v['cost']:.2f} $")


async def warte_auf_zug(run, stille_max: int):
    """Warten, bis der Zug fertig ist — abbrechen nur, wenn er sich nicht ruehrt.

    Hier stand frueher eine Gesamtdauer (300 s). Das war falsch gemessen: "bau
    ein neues Projekt" oder "produzier das Video" laeuft eine Stunde und ist die
    ganze Zeit fleissig — die Grenze haette genau die Auftraege abgeschossen,
    fuer die es die Firma gibt.

    Ein Zug darf also beliebig lange dauern. Was er nicht darf, ist
    STILLSTEHEN: ein haengender Prozess sendet gar kein Ereignis mehr. Gezaehlt
    wird deshalb die Zeit seit dem letzten Lebenszeichen (jedes emit setzt es).
    Die 30-Sekunden-Scheiben sind nur der Wecker; abgebrochen wird erst, wenn
    die Stille wirklich zu lang ist.
    """
    while True:
        rest = stille_max - (time.monotonic() - run.letztes_ereignis)
        if rest <= 0:
            raise asyncio.TimeoutError
        try:
            await asyncio.wait_for(asyncio.shield(run.task), timeout=min(rest, 30))
            return
        except asyncio.TimeoutError:
            continue


ZUSTELL_TASKS = set()   # Referenzen halten, sonst darf der GC einen laufenden Zug einsammeln


async def dispatcher_loop():
    await asyncio.sleep(1)
    wieder_aufnehmen()
    while True:
        try:
            tid, mid = await MAILBOX.get()
            task = asyncio.create_task(_zustellen(tid, mid))
            ZUSTELL_TASKS.add(task)
            task.add_done_callback(ZUSTELL_TASKS.discard)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[dispatcher] {type(e).__name__}: {e}", flush=True)


async def _zustellen(tid: str, mid: str):
    async with zug_lock(tid):
        await _zustellen_innen(tid, mid)


async def _zustellen_innen(tid: str, mid: str):
    global LIMIT_BIS
    t = auf.laden(tid)
    if not t or t["status"] not in ("neu", "laeuft"):
        return
    nachricht = next((e for e in auf.verlauf(tid) if e.get("id") == mid), None)
    if not nachricht:
        return
    if mid not in {n["id"] for n in auf.offene_nachrichten(tid)}:
        return      # laengst zugestellt — z.B. doppelt eingereiht nach einem "weiter"
    if PAUSIERT or LIMIT_BIS > time.time():
        # Not-Aus oder Nutzungslimit: die Nachricht bleibt im Umlauf und wird
        # zugestellt, sobald es weitergeht. Kein Anhalten, kein Kevin.
        await asyncio.sleep(15 if LIMIT_BIS > time.time() else 5)
        MAILBOX.put_nowait((tid, mid))
        return

    bremse, grund = guards.pruefe(t, nachricht, auf.verlauf(tid))
    if bremse:
        return auftrag_anhalten(t, bremse, grund)

    a = ag.load_agent(nachricht["an"], WORKSPACE)
    if not a or a["status"] == "fired":
        wer = nachricht["an"]
        return auftrag_anhalten(t, "unbekannt",
                               f"\u201e{wer}\u201c arbeitet hier nicht (mehr).")
    if a["status"] == "paused":
        # Pausiert heisst: bekommt gerade keine Arbeit. Vorher wurde der
        # Zustand zwar in der Akte gefuehrt, aber nirgends beachtet.
        return auftrag_anhalten(t, "unbekannt",
                               f"{a['name']} ist pausiert und nimmt gerade nichts an. "
                               f"Leite die Nachricht um oder hebe die Pause in der "
                               f"Personalakte auf.")

    def _start(x):
        x["status"] = "laeuft"
        x["in_arbeit"] = {"msg_id": mid, "run_id": "", "versuch":
                          (x.get("in_arbeit") or {}).get("versuch", 0) + 1}
        # Den Schritt VOR dem Zug buchen, nicht danach — sonst zaehlt die
        # Anzeige zwei parallel gestartete Zuege als einen.
        x["verbraucht"]["hops"] += 1
    t = await auftrag_aendern(tid, _start) or t

    async with TURN_SEM:
        run = start_agent_turn(a, t, nachricht)
        await auftrag_aendern(tid, lambda x: x["in_arbeit"].update({"run_id": run.id})
                             if x.get("in_arbeit") else None)
        feed(tid).emit({"type": "zug_start", "agent": a["slug"],
                        "name": a["name"], "color": a["color"], "run_id": run.id})

        def _ende(x):
            x["verbraucht"]["cost"] = round(x["verbraucht"]["cost"] + (run.cost_usd or 0), 4)
            # Je Mitarbeiter mitschreiben: nur so sieht Kevin, ob opus fuer
            # Selma das Geld wert ist oder wo ein Auftrag teuer wurde.
            je = x["verbraucht"].setdefault("je_agent", {})
            je[a["slug"]] = round(je.get(a["slug"], 0) + (run.cost_usd or 0), 4)
            # Mitschreiben statt nur anzeigen: nur so laesst sich zwischen zwei
            # Laeufen belegen, ob der Systemprompt noch aus dem Zwischenspeicher
            # kommt. .get() mit Vorgabe, weil aeltere Auftraege die Felder nicht
            # haben und beim Laden nicht nachgeruestet werden.
            for feld, wert in (("cache_read", run.cache_read),
                               ("cache_write", run.cache_write),
                               ("frisch", run.frisch)):
                x["verbraucht"][feld] = x["verbraucht"].get(feld, 0) + (wert or 0)
            if run.session_id:
                x["sessions"][a["slug"]] = run.session_id
            # NUR den eigenen Lauf abraeumen: laeuft laengst der naechste Zug,
            # gehoert in_arbeit ihm und darf nicht geloescht werden.
            if (x.get("in_arbeit") or {}).get("run_id") == run.id:
                x["in_arbeit"] = None

        async def _abschliessen(quittung=True):
            # In JEDEM Ausgang gleich: Quittung (sonst reiht wieder_aufnehmen
            # die Nachricht nach einem Neustart erneut ein), Kosten buchen,
            # Bus-Token einziehen (ein haengender Prozess darf nicht mehr
            # liefern), in_arbeit abraeumen — und der Oberflaeche sagen, dass
            # der Zug vorbei ist (sonst steht "arbeitet …" ewig im Verlauf).
            # Ohne Quittung nur, wenn der Zug WIEDERHOLT werden soll (Limit).
            if quittung:
                auf.quittieren(tid, mid)
            BUS_TOKENS.pop(run.bus_token, None)
            neu = await auftrag_aendern(tid, _ende) or t
            feed(tid).emit({"type": "zug_ende", "agent": a["slug"], "run_id": run.id})
            return neu

        try:
            await warte_auf_zug(run, a["max_stille_s"])
        except asyncio.TimeoutError:
            run.task.cancel()
            t = await _abschliessen()
            # an=Slug: Kevins "weiter" geht zurueck an den, der haengen blieb.
            # Der hat den Kontext in seiner Sitzung — ueber die
            # Geschaeftsfuehrung kostete es einen Zug Neubriefing.
            return auftrag_anhalten(t, "stille",
                                   f"Der Zug von {a['name']} hat sich "
                                   f"{a['max_stille_s'] // 60} Minuten nicht geruehrt — "
                                   f"er haengt vermutlich.", an=a["slug"])
        except asyncio.CancelledError:
            if not run.task.done():
                raise           # WIR wurden abgebrochen (Server faehrt herunter)
            # Der Lauf selbst wurde gestoppt (Stop-Knopf) — ohne diesen Zweig
            # stirbt die Zustellung hier, und der Auftrag bleibt fuer immer
            # auf "laeuft" mit gesetztem in_arbeit stehen.
            t = await _abschliessen()
            return auftrag_anhalten(t, "gestoppt",
                                   f"Der Zug von {a['name']} wurde von Hand gestoppt.",
                                   an=a["slug"])
        except Exception as e:
            print(f"[zug] {type(e).__name__}: {e}", flush=True)

    wiederholen = run.limit_bis > time.time()
    t = await _abschliessen(quittung=not wiederholen)

    if wiederholen:
        # Nutzungslimit der Subscription. Kein Fehler der Firma, also keine
        # Bremse und kein Kevin: der Zug wird wiederholt, sobald das Fenster
        # wieder offen ist. Vorher lief das als "stiller Zug" auf — und nach
        # einer Nacht standen alle Auftraege einzeln auf Rueckfrage.
        LIMIT_BIS = run.limit_bis
        wann = time.strftime("%H:%M", time.localtime(run.limit_bis))
        await auftrag_aendern(tid, lambda x: x["verbraucht"].__setitem__(
            "hops", max(0, x["verbraucht"]["hops"] - 1)))     # der Versuch zaehlt nicht
        e = auf.anhaengen(tid, {"art": "system", "text":
                               f"Nutzungslimit erreicht — der Zug von {a['name']} wird um "
                               f"{wann} Uhr wiederholt."})
        feed(tid).emit({"type": "msg", **e})
        if run.limit_bis not in LIMIT_GEMELDET:
            LIMIT_GEMELDET.add(run.limit_bis)
            tg_send(f"\u23f3 Nutzungslimit erreicht — die Firma macht um {wann} Uhr von "
                    f"selbst weiter.")
        MAILBOX.put_nowait((tid, mid))
        return

    if run.fehler and not getattr(run, "bus_calls", 0):
        # Login abgelaufen, Prozess abgestuerzt, API ueberlastet: der Zug hat
        # nicht gearbeitet. Das ist ein anderer Befund als "hat geantwortet,
        # aber nichts geliefert", und Kevin muss den Grund lesen koennen.
        return auftrag_anhalten(t, "fehler",
                               f"Der Zug von {a['name']} endete mit einem Fehler: "
                               f"{run.fehler[:400]}",
                               "Ursache beheben (Login, Netz), dann weiter — der Zug wird "
                               "wiederholt.", an=a["slug"])

    # Den Antworttext mitschreiben: fertige Laeufe raeumt gc_runs weg, der
    # Auftrag muss aber auch spaeter noch lesbar sein.
    if (run.last_text or "").strip():
        auf.anhaengen(tid, {"von": a["slug"], "an": "", "art": "gesagt",
                           "text": run.last_text.strip()[:20000]})

    if t["status"] != "laeuft":
        # Der Zug hat den Auftrag selbst beendet oder angehalten (liefern,
        # eskalieren, einstellen). Die Bremsen unten wuerden einen fertigen
        # Auftrag sonst gleich wieder auf "wartet_auf_kevin" kippen.
        feed(tid).emit({"type": "stand", **t["verbraucht"]})
        return

    if not getattr(run, "bus_calls", 0):
        offen = ausstehend(a["slug"], auf.verlauf(tid))
        if offen:
            # Kein stiller Zug, sondern Warten: er hat Leute beauftragt, deren
            # Ergebnis noch fehlt — etwa Tessas Befund gelesen, waehrend Cody
            # schon an der Nachbesserung sitzt. Der naechste Zug kommt von
            # selbst, sobald ein Ergebnis eintrifft.
            e = auf.anhaengen(tid, {"art": "system",
                                   "text": f"{a['name']} wartet auf: {', '.join(offen)}."})
            feed(tid).emit({"type": "msg", **e})
            feed(tid).emit({"type": "stand", **t["verbraucht"]})
            return
        liegt = [n for n in auf.offene_nachrichten(tid)
                 if n.get("an") == a["slug"] and n.get("id") != mid]
        if liegt:
            # Auch kein stiller Zug: die naechste Nachricht an ihn ist schon
            # eingereiht (bei paralleler Verteilung kommen zwei Ergebnisse
            # kurz nacheinander, das zweite wartet hinter der Sperre). Am
            # 11.09.2026 riss hier die Bremse, obwohl Tessas Ergebnis fuer
            # Lumina laengst im Postfach lag.
            e = auf.anhaengen(tid, {"art": "system",
                                   "text": f"{a['name']} ist gleich wieder dran: "
                                   + ", ".join(f"{n.get('art')} von {n.get('von')}" for n in liegt)
                                   + " liegt schon vor."})
            feed(tid).emit({"type": "msg", **e})
            feed(tid).emit({"type": "stand", **t["verbraucht"]})
            return
        # Ein Zug, der nichts an den Bus gegeben hat, ist eine Sackgasse: der
        # Auftrag wuerde stehenbleiben, ohne dass es jemand merkt.
        zuletzt = " ".join((run.last_text or "").split())[:300]
        return auftrag_anhalten(
            t, "stiller_zug",
            f"{a['name']} hat geantwortet, aber weder geliefert noch weitergegeben — "
            f"der Auftrag würde sonst unbemerkt stehenbleiben."
            + (f" Zuletzt gesagt: \u201e{zuletzt}\u201c" if zuletzt else ""),
            f"Sag {a['name']} in einem Satz, wie es weitergeht — etwa \u201eLiefer den "
            f"Stand an mich\u201c oder \u201eGib das an <Kollege> weiter\u201c. Meist reicht "
            f"WEITERMACHEN ohne Text: dann bekommt {a['name']} \u201eMach bitte weiter\u201c "
            f"und entscheidet selbst.",
            an=a["slug"])

    bremse, grund = guards.pruefe_nach_zug(t, auf.verlauf(tid))
    if bremse:
        return auftrag_anhalten(t, bremse, grund)
    feed(tid).emit({"type": "stand", **t["verbraucht"]})


def wieder_aufnehmen():
    """Nach einem Neustart: was lief, aber nicht zugestellt wurde.

    Ehrlich bleiben: ein wiederholter Zug wiederholt auch seine Nebenwirkungen.
    Der Agent koennte dieselbe Datei zweimal schreiben — oder schlimmer, zweimal
    halb. Es gibt keine saubere Art, einen LLM-Zug transaktional zu machen, also
    wird es benannt statt uebertuencht: Warnhinweis in der Nachricht, und ab dem
    dritten Versuch entscheidet Kevin.
    """
    for t in auf.alle():
        if t["status"] != "laeuft":
            continue
        offen = auf.offene_nachrichten(t["id"])
        versuch = (t.get("in_arbeit") or {}).get("versuch", 0)
        if versuch >= 3:
            auftrag_anhalten(t, "neustart",
                            f"Dieser Zug wurde {versuch} Mal durch einen Neustart "
                            f"unterbrochen. Da stimmt etwas nicht.")
            continue
        if not offen:
            # Status "laeuft", aber nichts mehr zuzustellen: der Zug ist beim
            # Absturz verlorengegangen. Ohne diesen Zweig bliebe der Auftrag
            # fuer immer auf "laeuft" stehen, ohne dass je wieder etwas
            # passiert — sichtbar haengen ist besser als still haengen.
            auftrag_anhalten(t, "neustart",
                            "Der Auftrag lief beim Neustart, aber es ist keine "
                            "offene Nachricht mehr da. Der letzte Zug ging verloren.")
            continue
        # Den Zaehler BEHALTEN: _start rechnet versuch+1 auf das, was hier
        # steht. Mit None stuende er nach jedem Neustart wieder auf 1, und der
        # Schutzschalter oben koennte nie ausloesen.
        t["in_arbeit"] = {"msg_id": "", "run_id": "", "versuch": versuch}
        auf.speichern(t)
        for n in offen:
            auf.anhaengen(t["id"], {
                "art": "system",
                "text": "[Der Server wurde neu gestartet. Pruefe erst den Zustand "
                        "der Dateien, bevor du weiterarbeitest — dein vorheriger "
                        "Zug wurde mittendrin abgebrochen.]"})
            MAILBOX.put_nowait((t["id"], n["id"]))


def bus_config(slug: str, token: str, ticket_id: str = "") -> str:
    """Die MCP-Konfiguration fuer einen Lauf — eine Stelle, zwei Aufrufer."""
    return json.dumps({"mcpServers": {"firma": {
        "command": sys.executable or "python3",
        "args": [str(BASE_DIR / "team_mcp.py")],
        "env": {"FIRMA_AGENT": slug, "FIRMA_AUFTRAG": ticket_id,
                "FIRMA_TOKEN": token, "FIRMA_BASE": bus_base(),
                "FIRMA_AUTH": bus_auth_header(),
                "FIRMA_NUTZER": ag.anrede("Kevin")}}}})


def start_agent_chat(a: dict, prompt: str, images=None):
    """Ein Zug im Direktgespräch.

    Anders als in der Auftragsarbeit gibt es hier NUR die Gedaechtnis-Werkzeuge.
    Wer mit Kevin redet, soll nicht nebenbei Kollegen beauftragen — will er
    Arbeit erledigt haben, legt er einen Auftrag an.
    """
    d = ag.AGENTS_DIR / a["slug"]
    d.mkdir(parents=True, exist_ok=True)
    spf = d / ".systemprompt"
    ag._atomic(spf, agent_system_prompt(a, WORKSPACE))
    sid = chat_session_id(a["slug"])
    token = uuid.uuid4().hex
    BUS_TOKENS[token] = (a["slug"], "")
    cmd = build_claude_cmd(mode=a["permission_mode"], model=a["model"],
                           effort=a["effort"], session_id=sid or None,
                           system_prompt_file=spf,
                           mcp_config=bus_config(a["slug"], token),
                           allowed_tools=list(a["allowed_tools"])
                           + [f"mcp__firma__{w}" for w in CHAT_WERKZEUGE])
    return spawn(cmd, a["cwd"], a["model"], prompt, sid or None,
                  agent_slug=a["slug"], bus_token=token)


def kevin_ziel(t: dict, an_wunsch: str) -> tuple:
    """Wohin Kevins Wort geht und als WAS — eine Stelle fuer /antwort und /say.

    Kevins Antwort an den, der eskaliert hat, ist eine ANTWORT — kein neuer
    Auftrag. Der Unterschied entscheidet, wer am Ende das Ergebnis bekommt:
    `liefern` geht an den, der zuletzt einen AUFTRAG geschickt hat. Stand da
    "kevin", lieferte der Mitarbeiter an Kevin, der Auftrag galt als fertig,
    und die Geschaeftsfuehrung sah das Ergebnis nie. Genau so ist Lumina bei
    der Werkstatt uebersprungen worden, und Veritas kam nie zum Pruefen.

    Das war in /antwort laengst repariert — /say (die Eingabezeile unter dem
    Auftrag) schickte aber weiter alles als Auftrag. Wer unten tippte statt im
    roten Balken, loeste denselben Fehler erneut aus. Deshalb jetzt EINE
    Funktion fuer beide.

    Leitet Kevin dagegen ausdruecklich an jemand anderen um, ist es sehr wohl
    ein neuer Auftrag — dann hat er die Person selbst beauftragt.
    """
    esk = t.get("eskalation") or {}
    an = an_wunsch or esk.get("an") or t["owner"]
    art = "auftrag" if (an_wunsch or not esk or an == t["owner"]) else "antwort"
    return an, art


def nachliefern(tid: str):
    """Alles wieder einreihen, was zugestellt werden sollte, als der Auftrag anhielt.

    Faellt eine Bremse, waehrend im Postfach noch eine Nachricht liegt (bei
    paralleler Verteilung der Normalfall: Lumina beauftragt Cody, geht im
    naechsten Zug still, Codys Auftrag ist noch unterwegs), wirft der
    Dispatcher sie weg — der Auftrag ist ja nicht mehr "laeuft". Nach Kevins
    "weiter" kaeme sie nie wieder. Doppelte Zustellung verhindert die
    Quittungspruefung in _zustellen_innen.
    """
    for n in auf.offene_nachrichten(tid):
        MAILBOX.put_nowait((tid, n["id"]))


async def kevin_weiter(tid: str, an_wunsch: str, text: str) -> dict | None:
    """Kevin laesst einen wartenden Auftrag weiterlaufen — unter der Sperre.

    Vorher luden /antwort und /say den Auftrag, warteten auf req.json() und
    speicherten ihn zurueck. Schloss in der Luecke der claude-Prozess seine
    Buchung ab (Kosten, Sitzungs-ID), war sie ueberschrieben — und der
    Mitarbeiter fing beim naechsten Zug ohne seinen Kontext an.
    """
    ziel = {}

    def _weiter(x):
        if x["status"] == "wartet_auf_kevin":
            # Kevin hat hingeschaut und sagt weiter — also faengt die Zaehlung
            # der Bremsen von vorn an. Kein Nachlegen von Zahlen: eine
            # Ausloesung soll eine Entscheidung erzwingen, und die hat er
            # gerade getroffen. Ein Einwurf in einen LAUFENDEN Auftrag ist
            # keine Freigabe und laesst die Zaehler stehen.
            wartezeit_abziehen(x)
            guards.freigeben(x)
        ziel["an"], ziel["art"] = kevin_ziel(x, an_wunsch)
        x["status"] = "laeuft"
        x["eskalation"] = None

    t = await auftrag_aendern(tid, _weiter)
    if t:
        nachliefern(tid)
        bus_einreihen(t, "kevin", ziel["an"], ziel["art"], text or "Mach bitte weiter.")
    return t

# ---------- Start und Stopp ----------
_DISPATCHER = {"task": None, "loop": None}


def starten():
    """Dispatcher in der laufenden Ereignisschleife anwerfen (idempotent).

    Aus dem Start des Servers UND aus jedem Aufruf, der Arbeit einreiht: so läuft
    die Firma auch dort, wo kein Start-Hook feuert (Tests, `--lifespan off`).
    Die Warteschlange bindet sich an die Schleife, in der sie zuerst benutzt
    wird — wechselt die Schleife (Tests), wird sie neu angelegt.
    """
    global MAILBOX, TURN_SEM
    loop = asyncio.get_running_loop()
    if _DISPATCHER["loop"] is not loop:
        MAILBOX = asyncio.Queue()
        TURN_SEM = asyncio.Semaphore(PARALLEL)
        _DISPATCHER["loop"] = loop
        _DISPATCHER["task"] = None
    t = _DISPATCHER["task"]
    if t is None or t.done():
        _DISPATCHER["task"] = loop.create_task(dispatcher_loop())


def stoppen():
    t = _DISPATCHER["task"]
    if t is not None and not t.done():
        t.cancel()
    _DISPATCHER["task"] = None
