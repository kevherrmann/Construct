"""Der Firmen-Bus: was passiert, wenn ein Mitarbeiter ein Werkzeug aufruft.

Gegenstelle zu team_mcp.py. Jeder Aufruf landet hier und kehrt SOFORT zurück —
nie wartet ein Zug auf einen Menschen oder einen anderen Prozess. Deshalb ist
jeder Zug kurz begrenzt, und ein Neustart kostet höchstens einen wiederholten
Zug statt eines hängenden Prozessbaums.
"""
import asyncio
import time

from server.runs import RUNS
from server.core import WORKSPACE
from server.team import agents as ag
from server.team import anleitungen as anl
from server.team import auftraege as auf
from server.team import engine
from server.team import guards
from server.team import kontrast, rechner
from server.team.gedaechtnis import CHAT_WERKZEUGE, gedaechtnis_eindicken, mem_lock

USER_LOCK = asyncio.Lock()      # die geteilte USER.md hat genau EINEN Schreiber
ANLEITUNG_LOCK = asyncio.Lock()  # dito fuer die gemeinsamen Anleitungen

SOFORT = ("zugestellt \u2014 beende jetzt deinen Zug. Die Antwort erreicht dich "
          "als neue Nachricht.")
# Werkzeuge, die eine Nachricht in den Auftrag geben. Davon eine pro Zug \u2014
# ausser `beauftragen` an verschiedene Leute, davon bis zu:
ROUTING = ("beauftragen", "fragen", "antworten", "liefern", "eskalieren", "einstellen")
BEAUFTRAGEN_MAX = 3


def _bus_fehler(text):
    # Absichtlich als Werkzeug-FEHLER zurueck, nicht als stilles Verschlucken:
    # der Agent sieht ihn und korrigiert sich. Ein raetselhafter Stillstand
    # waere viel schlimmer.
    return {"text": text, "error": True}


async def bus_aufruf(body: dict) -> dict:
    """Ein Werkzeugaufruf eines Mitarbeiters. Gibt {"text", "error"?} zurück."""
    token = str(body.get("token") or "")
    if token not in engine.BUS_TOKENS:
        return _bus_fehler("Dieser Zug ist beendet. Der Bus nimmt nichts mehr an.")
    slug, tid = engine.BUS_TOKENS[token]
    werkzeug = str(body.get("tool") or "")
    args = body.get("args") or {}
    print(f"[bus] {slug} -> {werkzeug}", flush=True)
    a = ag.load_agent(slug, WORKSPACE)
    # Im Direktgespraech gibt es keinen Auftrag — dann sind nur die
    # Gedaechtnis-Werkzeuge erlaubt (s. CHAT_WERKZEUGE).
    t = auf.laden(tid) if tid else None
    if not a:
        return _bus_fehler("Personalakte nicht auffindbar.")
    if not t and werkzeug not in CHAT_WERKZEUGE:
        return _bus_fehler(f"„{werkzeug}\u201c geht nur in einem Auftrag. "
                           f"Hier redest du direkt mit Kevin.")

    run = next((r for r in RUNS.values() if getattr(r, "bus_token", "") == token), None)

    def zaehl():
        if run is not None:
            run.bus_calls += 1
            run.bus_letztes = werkzeug
        else:
            # Ohne Run kann der Dispatcher den Zug nicht als "hat geliefert"
            # erkennen und wuerde faelschlich anhalten. Sichtbar machen.
            print(f"[bus] WARNUNG: kein Lauf zu token fuer {slug}/{werkzeug}", flush=True)

    if werkzeug in ROUTING:
        if t and t["status"] == "abgebrochen":
            # Kevin hat abgebrochen, waehrend dieser Zug noch lief. Ein
            # `liefern` jetzt wuerde den Auftrag wieder auf "fertig" setzen.
            return _bus_fehler("Kevin hat diesen Auftrag abgebrochen. Beende deinen Zug, "
                               "ohne weiter zu arbeiten.")
        if run is not None and run.bus_calls >= 1:
            # "Ein Zug, eine Nachricht" — vorher stand das nur in PROTOCOL.md,
            # und der Bus liess `fragen` gefolgt von `liefern` durch. Die
            # Antwort auf die Frage erreichte dann jemanden, der laengst
            # abgeliefert hatte, und der lieferte ein zweites Mal.
            #
            # Einzige Ausnahme: mehrere `beauftragen` an VERSCHIEDENE Leute, wenn
            # ein Verteiler unabhaengige Teile parallel vergibt.
            mehrfach = (werkzeug == "beauftragen" and run.bus_letztes == "beauftragen")
            if not mehrfach:
                return _bus_fehler(
                    f"Du hast in diesem Zug schon `{run.bus_letztes}` aufgerufen — ein "
                    f"Zug, eine Nachricht. Beende jetzt deinen Zug; was du noch sagen "
                    f"willst, sagst du, wenn du wieder dran bist.")
            if len(run.bus_ziele) >= BEAUFTRAGEN_MAX:
                return _bus_fehler(
                    f"Hoechstens {BEAUFTRAGEN_MAX} Kollegen pro Zug. Den Rest vergibst du, "
                    f"wenn die ersten Ergebnisse da sind.")

    # --- nur lesen ---
    if werkzeug == "rechnen":
        # Ueberall erlaubt, auch ohne Auftrag: ein Rechenfehler ist in einem
        # Gespraech genauso schaedlich wie in einem Auftrag.
        try:
            return {"text": rechner.calculate(str(args.get("ausdruck") or ""))}
        except rechner.CalcError as e:
            return _bus_fehler(str(e))

    if werkzeug == "kontrast":
        try:
            return {"text": kontrast.bericht(str(args.get("vorne") or ""),
                                             str(args.get("hinten") or ""))}
        except kontrast.FarbFehler as e:
            return _bus_fehler(str(e))

    if werkzeug == "belegschaft":
        return {"text": "\n".join(
            f"{x['slug']}: {x['name']}, {x['title']} "
            f"({'darf verteilen' if x['can_delegate'] else 'arbeitet selbst'}; "
            f"{ag.faehigkeiten(x)}"
            f"{'; PAUSIERT — nimmt gerade nichts an' if x['status'] == 'paused' else ''})"
            for x in ag.list_agents(WORKSPACE))}

    if werkzeug == "notiz":
        e = auf.anhaengen(tid, {"von": slug, "an": "", "art": "notiz",
                               "text": str(args.get("text"))[:4000]})
        engine.feed(tid).emit({"type": "msg", **e})
        return {"text": "notiert (zaehlt nicht als Schritt)"}

    if werkzeug == "auftrag_anlegen":
        # Die Bruecke vom Gespraech in die Auftragsarbeit: Kevin sagt "kuemmer
        # dich drum", und daraus wird ein richtiger Auftrag mit Verlauf und
        # Bremsen — statt dass der Mitarbeiter im Gespraech drauflosarbeitet.
        if t:
            return _bus_fehler("Du bist schon in einem Auftrag. Liefere oder eskaliere.")
        chef = ag.load_agent(ag.OWNER_SLUG, WORKSPACE) or a
        neu = auf.neu(str(args.get("titel") or "")[:120] or "Auftrag",
                     str(args.get("brief") or ""), owner=chef["slug"], cwd=chef["cwd"])
        neu["status"] = "laeuft"
        auf.speichern(neu)
        engine.bus_einreihen(neu, "kevin", chef["slug"], "auftrag",
                      f"{neu['brief']}\n\n(Aufgenommen von {a['name']} "
                      f"aus dem Gespräch mit Kevin.)")
        return {"text": f"Auftrag „{neu['titel']}\u201c angelegt (Nummer {neu['id']}). "
                        f"{chef['name']} verteilt ihn. Sag Kevin Bescheid."}

    if werkzeug == "merken":
        d = ag.AGENTS_DIR / slug
        neu_txt = " ".join(str(args.get("text") or "").split())[:400]
        if not neu_txt:
            return _bus_fehler("leerer Eintrag")
        eingedickt = False
        async with mem_lock(slug):
            # UNGEKAPPT lesen: die gekappte Fassung zurueckzuschreiben wuerde bei
            # einer vollen Datei mit jedem Eintrag das Ende (die juengsten
            # Erkenntnisse) abschneiden — und trotzdem "gemerkt" melden.
            alt = ag._read_capped(d / "MEMORY.md", 10 ** 9)
            if neu_txt.lower() in alt.lower():
                return {"text": "steht schon in deinem Gedaechtnis"}
            if len(alt) + len(neu_txt) + 4 > ag.MAX_MEMORY:
                # Voll: JETZT eindicken und danach anhaengen. Vorher stand hier
                # nur eine Fehlermeldung, die auf eine Verdichtung im
                # Direktgespraech verwies — die bei einem Mitarbeiter, mit dem
                # Kevin selten redet, nie kam. Der Agent lernte ab da nichts
                # mehr, dauerhaft und unbemerkt.
                eingedickt = await gedaechtnis_eindicken(a)
                if eingedickt:
                    alt = ag._read_capped(d / "MEMORY.md", 10 ** 9)
            if len(alt) + len(neu_txt) + 4 > ag.MAX_MEMORY:
                return _bus_fehler(
                    f"Dein Gedaechtnis ist voll ({len(alt)} von {ag.MAX_MEMORY} "
                    f"Zeichen) und liess sich nicht eindicken. Sag Kevin, dass er "
                    f"in agents/{slug}/MEMORY.md aufraeumen muss.")
            ag._atomic(d / "MEMORY.md", (alt.rstrip("\n") + "\n- " + neu_txt).strip() + "\n")
        return {"text": "gemerkt, dein Gedaechtnis wurde dabei eingedickt"
                        if eingedickt else "gemerkt"}

    if werkzeug == "user_merken":
        async with USER_LOCK:
            ok, meldung = ag.user_append(args.get("fakt"), slug)
        return {"text": meldung} if ok else _bus_fehler(meldung)

    if werkzeug == "anleitung":
        name = str(args.get("name") or "").strip()
        x = anl.lesen(name)
        if not x:
            # Die vorhandenen Namen mitgeben statt nur "gibt's nicht": das
            # Modell hat sich meist nur vertippt, und ohne die Liste raet es
            # ein zweites Mal.
            da = ", ".join(y["name"] for y in anl.alle()) or "keine"
            return _bus_fehler(f"Keine Anleitung namens '{name}'. Vorhanden: {da}")
        anl.benutzt_vermerken(name)
        return {"text": f"# Anleitung: {x['name']}\n\n{x['text']}"}

    if werkzeug == "anleitung_anlegen":
        async with ANLEITUNG_LOCK:
            ok, meldung = anl.anlegen(str(args.get("name") or ""),
                                      str(args.get("wann") or ""),
                                      str(args.get("text") or ""), slug)
        return {"text": meldung} if ok else _bus_fehler(meldung)

    # --- Nachrichten an Kollegen ---
    if werkzeug in ("beauftragen", "fragen"):
        if werkzeug == "beauftragen" and not a["can_delegate"]:
            return _bus_fehler(f"{a['name']} darf keine Arbeit verteilen. "
                               f"Liefere dein Ergebnis oder eskaliere.")
        an = str(args.get("an") or "").strip()
        ziel = ag.load_agent(an, WORKSPACE)
        if not ziel or ziel["status"] == "fired":
            namen = ", ".join(x["slug"] for x in ag.list_agents(WORKSPACE))
            return _bus_fehler(f"„{an}\u201c gibt es nicht. Moeglich: {namen}")
        if ziel["status"] == "paused":
            return _bus_fehler(f"{ziel['name']} ist pausiert und nimmt gerade nichts an. "
                               f"Nimm jemand anderen oder eskaliere.")
        if an == slug:
            return _bus_fehler("Du kannst dich nicht selbst beauftragen.")
        if run is not None and an in run.bus_ziele:
            return _bus_fehler(f"{ziel['name']} hast du in diesem Zug schon beauftragt. "
                               f"Pack alles in EIN Briefing — der zweite Auftrag kaeme "
                               f"erst nach dem ersten Ergebnis an.")
        if werkzeug == "beauftragen" and a.get("delegates_to") and an not in a["delegates_to"]:
            return _bus_fehler(f"{a['name']} darf laut Personalakte nur an "
                               f"{', '.join(a['delegates_to'])} verteilen.")
        letzte = next((e for e in reversed(auf.verlauf(tid)) if e.get("an") == slug), {})
        tiefe = int(letzte.get("tiefe") or 0) + 1
        if tiefe > guards.TIEFE_MAX:
            return _bus_fehler(
                f"Die Aufgabe waere damit {tiefe} Mal weitergereicht (erlaubt: "
                f"{guards.TIEFE_MAX}). Mach es selbst oder eskaliere.")
        text = str(args.get("auftrag") or args.get("frage") or "")
        groesse = ""
        if werkzeug == "beauftragen":
            groesse = str(args.get("groesse") or "normal").strip().lower()
            if groesse not in auf.GROESSEN:
                return _bus_fehler(f"groesse muss eins von {', '.join(auf.GROESSEN)} sein.")
            # Klein heisst: eine Person, deren `liefern` direkt zu Kevin geht.
            # Nur die Geschaeftsfuehrung schliesst so ab; weiter unten in der
            # Kette bleibt es ein normales Teilstueck.
            if groesse == "klein" and slug != t["owner"]:
                groesse = "normal"
        engine.bus_einreihen(t, slug, an, "auftrag" if werkzeug == "beauftragen" else "frage",
                      text, tiefe=tiefe, groesse=groesse)
        zaehl()
        if run is not None and werkzeug == "beauftragen":
            run.bus_ziele.append(an)
            if groesse == "klein":
                return {"text": (f"zugestellt als Kleinauftrag: {ziel['name']}s Ergebnis "
                                 "geht direkt an Kevin und schliesst den Auftrag ab. "
                                 "Beende deinen Zug — du bist hier fertig.")}
            return {"text": ("zugestellt. Hast du noch einen UNABHAENGIGEN Teil fuer "
                             "jemand anderen, beauftrage ihn jetzt — sonst beende deinen "
                             "Zug. Die Ergebnisse erreichen dich einzeln als neue "
                             "Nachrichten.")}
        return {"text": SOFORT}

    if werkzeug in ("antworten", "liefern"):
        # WEM man liefert, haengt davon ab, wer einen BEAUFTRAGT hat — nicht
        # davon, wer zuletzt geschrieben hat. Wer eine Aufgabe von Lumina
        # bekommt, zwischendurch einen Kollegen fragt und dessen Antwort
        # erhaelt, liefert trotzdem an Lumina zurueck.
        gesucht = ("auftrag",) if werkzeug == "liefern" else ("frage",)
        empf = next((e.get("von") for e in reversed(auf.verlauf(tid))
                     if e.get("an") == slug and e.get("art") in gesucht and e.get("von")), "")
        if not empf:
            empf = next((e.get("von") for e in reversed(auf.verlauf(tid))
                         if e.get("an") == slug and e.get("von")), "") or t["owner"]
        text = str(args.get("antwort") or args.get("ergebnis") or "")
        dateien = [str(x) for x in (args.get("dateien") or [])][:20]
        # Fertig ist der Auftrag, wenn der Auftraggeber selbst liefert — oder
        # wenn direkt an Kevin geliefert wird (er hat jemanden am Owner vorbei
        # beauftragt). "kevin" hat keine Personalakte; ihn als Empfaenger in
        # den Bus zu geben, riss frueher die Bremse "unbekannt".
        fertig = empf == slug or (werkzeug == "liefern" and (slug == t["owner"] or empf == "kevin"))
        if (werkzeug == "liefern" and not fertig and empf == t["owner"]
                and auf.kleinauftrag_direkt(auf.verlauf(tid), slug, t["owner"])):
            # Kleinauftrag: die Geschaeftsfuehrung hat genau diese eine Person
            # beauftragt und vorab entschieden, dass ihr Ergebnis ohne
            # Zusammenfassung zu Kevin darf. Spart den teuersten Zug des
            # Auftrags — den, in dem Opus zehn Zeilen in acht uebersetzt.
            fertig = True

        def _buchen(x):
            # Unter der Ticket-Sperre, nicht mit dem beim Aufruf geladenen t:
            # parallel bucht der Dispatcher hops/in_arbeit, und ein veralteter
            # Stand wuerde das ueberschreiben.
            for pf in dateien:
                x["artefakte"].append({"pfad": pf, "von": slug, "ts": time.time(),
                                       "sha": engine._sha(pf)})
            # Nur Lieferungen von Schreibenden zaehlen (siehe guards.py).
            schreibt = bool({"Write", "Edit"} & set(a["allowed_tools"]))
            if dateien:
                x["wache"]["ohne_artefakt"] = 0
            elif werkzeug == "liefern" and schreibt and not fertig:
                x["wache"]["ohne_artefakt"] = x["wache"].get("ohne_artefakt", 0) + 1
            if fertig:
                x["status"] = "fertig"
                x["ergebnis"] = text[:20000]
        t = await engine.auftrag_aendern(tid, _buchen) or t
        if fertig:
            # Der ausgelagerte Systemprompt dieses Auftrags wird nicht mehr gebraucht.
            for spf in ag.AGENTS_DIR.glob(f"*/.sysprompt-{tid}"):
                spf.unlink(missing_ok=True)
            # Jeder, der mitgearbeitet hat, bekommt den Auftrag in seine Akte.
            # Das ist die Grundlage dafuer, dass Lumina beim naechsten Mal
            # denselben Fachmann wieder waehlt.
            beteiligt = {}
            for eintrag in auf.verlauf(tid):
                for wer in (eintrag.get("von"), eintrag.get("an")):
                    if wer and wer != "kevin":
                        beteiligt.setdefault(wer, set())
                for f in (eintrag.get("dateien") or []):
                    if eintrag.get("von"):
                        beteiligt.setdefault(eintrag["von"], set()).add(f)
            # NICHT "dateien" als Schleifenvariable: das ueberschrieb die Liste
            # des Aufrufs mit einem set, und das anschliessende anhaengen()
            # brach mit "Object of type set is not JSON serializable" ab —
            # der Auftrag galt danach als nicht geliefert, obwohl alles fertig war.
            # Pruefstand-Auftraege bleiben draussen: die Historie haengt am
            # Systemprompt, und nach ein paar Laeufen bestand Chantis Akte zu
            # 43 von 43 Zeilen aus Testauftraegen — die echte Arbeit war raus.
            if not t["titel"].startswith(auf.TEST_MARKE):
                for wer, wessen_dateien in beteiligt.items():
                    rolle = "geleitet" if wer == t["owner"] else "mitgearbeitet"
                    ag.historie_eintragen(wer, t["titel"], rolle, sorted(wessen_dateien))
            e = auf.anhaengen(tid, {"von": slug, "an": "kevin", "art": "ergebnis",
                                   "text": text[:20000], "dateien": dateien})
            engine.feed(tid).emit({"type": "msg", **e})
            engine.feed(tid).emit({"type": "fertig"})
            engine.bruecke_abschluss(t)
            titel = t["titel"]
            engine.tg_send(f"\u2705 Auftrag \u201e{titel}\u201c ist fertig\n\n{text[:600]}")
            zaehl()
            return {"text": "Der Auftrag ist abgeschlossen. Beende deinen Zug."}
        if empf == "kevin":
            # Antwort auf eine Frage von Kevin: er liest sie in der Oberflaeche,
            # zustellen laesst sie sich nicht — also wartet der Auftrag auf ihn.
            e = auf.anhaengen(tid, {"von": slug, "an": "kevin", "art": "antwort",
                                   "text": text[:20000], "dateien": dateien})
            engine.feed(tid).emit({"type": "msg", **e})
            zaehl()
            engine.auftrag_anhalten(t, "eskaliert", f"{a['name']} hat dir geantwortet.",
                            "Wie soll es weitergehen?", an=slug)
            return {"text": "Antwort ist bei Kevin, der Auftrag wartet auf ihn. Beende deinen Zug."}
        engine.bus_einreihen(t, slug, empf, "ergebnis" if werkzeug == "liefern" else "antwort",
                      text, dateien=dateien)
        zaehl()
        return {"text": SOFORT}

    if werkzeug == "eskalieren":
        zaehl()
        engine.auftrag_anhalten(t, "eskaliert", str(args.get("grund") or ""),
                        str(args.get("frage") or ""), an=slug)
        return {"text": "Kevin ist informiert, der Auftrag pausiert. Beende deinen Zug."}

    if werkzeug == "einstellen":
        if not a["can_hire"]:
            return _bus_fehler(f"{a['name']} darf niemanden einstellen.")
        zaehl()

        def _einstellung(x):
            x["status"] = "wartet_auf_einstellung"
            x["einstellung"] = {"rolle": str(args.get("rolle") or ""),
                                "warum": str(args.get("warum") or ""),
                                "kandidaten": [], "runden": 0, "seit": time.time()}
            x["in_arbeit"] = None
        t = await engine.auftrag_aendern(tid, _einstellung) or t
        engine.feed(tid).emit({"type": "einstellung", **t["einstellung"]})
        rolle = t["einstellung"]["rolle"]
        engine.tg_send(f"\U0001f465 Auftrag \u201e{t['titel']}\u201c: Lumina moechte "
                f"jemanden fuer \u201e{rolle}\u201c einstellen.")
        return {"text": "Anfrage gestellt. Kevin waehlt aus. Beende deinen Zug."}

    return _bus_fehler(f"Unbekanntes Werkzeug: {werkzeug}")
