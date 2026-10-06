#!/usr/bin/env python3
"""Der Pruefstand — misst, ob die Firma noch das tut, was sie tun soll.

Warum es das gibt: Die Firma wird nicht ueber Code gesteuert, sondern ueber
Text. PROTOCOL.md, HAUSSTIL.md, die SOUL.md jedes Mitarbeiters, die Grenzen in
guards.py — jede Zeile davon aendert das Verhalten der ganzen Firma, und keine
davon laesst sich mit einem Unittest pruefen. Bisher war die einzige Antwort auf
"ist es dadurch besser geworden?" ein Bauchgefuehl nach einem Testauftrag.

Hier laufen stattdessen feste Auftraege gegen die laufende Firma, und was
dabei herauskommt, wird gemessen: Ist der Auftrag fertig geworden? Wie viele
Zuege hat er gebraucht? Was hat er gekostet? Ist eine Bremse gefallen — und
war es die richtige? Liegen die Dateien da, die liegen sollten?

Bewusst KEIN Modell als Schiedsrichter. Ein zweites Sprachmodell, das Noten
verteilt, ist teuer, schwankt zwischen zwei Laeufen und misst am Ende sich
selbst. Hier wird nur geprueft, was hart nachweisbar ist: Zustand, Zahlen,
Dateien, Stichworte. Ein Fall, dessen Ergebnis sich nicht so pruefen laesst,
ist als Fall schlecht geschnitten und gehoert umgeschrieben.

Ein Fall ist eine Datei, kein Datensatz — dieselbe Haltung wie bei den
Personalakten in server/team/agents.py: man muss einen Fall im Editor aufmachen,
anpassen und wieder laufen lassen koennen, ohne dieses Programm anzufassen.

    scripts/pruefstand/faelle/<name>.md       der Auftrag + was dabei herauskommen muss
    scripts/pruefstand/faelle-<name>/         eigene Fallsammlungen (nicht im Git)
    scripts/pruefstand/laeufe/<stempel>.json  was tatsaechlich herauskam, pro Lauf einer
    scripts/pruefstand/arbeit/<name>/         der Ordner, in dem der Fall arbeiten darf
    scripts/pruefstand/firma/                 die Firma, an der gemessen wird (eine Kopie)

Benutzung:

    python3 scripts/pruefstand.py lauf                 alle Faelle
    python3 scripts/pruefstand.py lauf --nur smoke     nur passende
    python3 scripts/pruefstand.py lauf --budget 1.00   abbrechen, bevor es teuer wird
    python3 scripts/pruefstand.py lauf --faelle faelle-<name>
    python3 scripts/pruefstand.py liste                welche Faelle es gibt
    python3 scripts/pruefstand.py vergleich            letzter Lauf gegen den davor
    python3 scripts/pruefstand.py aufraeumen           Eval-Auftraege und Arbeitsordner weg
    python3 scripts/pruefstand.py firma-vorbereiten --aus ~/projects/factoria

Nur Standardbibliothek: der Pruefstand muss auch dann noch laufen, wenn an
FACTORIAs Abhaengigkeiten gerade geschraubt wird.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from base64 import b64encode
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PS_DIR = Path(__file__).resolve().parent / "pruefstand"
FAELLE_DIR = PS_DIR / "faelle"
LAEUFE_DIR = PS_DIR / "laeufe"
ARBEIT_DIR = PS_DIR / "arbeit"
# Die Firma, an der gemessen wird: eine Kopie, nicht die echte. Der Prüfstand
# lässt Aufträge laufen, legt Anleitungen an und schreibt Historie in die Akten —
# das gehört nicht in die Belegschaft, mit der man arbeitet. Leer = beim ersten
# Start aus den mitgelieferten Vorlagen aufgebaut; `firma-vorbereiten` füllt sie
# mit einer bestehenden Belegschaft (etwa der aus FACTORIA).
FIRMA_DIR = PS_DIR / "firma"
PORT = int(os.environ.get("CONSTRUCT_PRUEFSTAND_PORT", "8798"))

# Woran man einen Auftrag des Pruefstands erkennt — im Titel, damit er auch in
# der Weboberflaeche sofort als Testauftrag zu sehen ist und aufraeumen() ihn
# von echten Auftraegen unterscheiden kann. Dieselbe Marke steht in
# server/team/auftraege.py (TEST_MARKE): der Server schreibt fuer solche Auftraege
# keine Historie in die Personalakten.
MARKE = "[eval]"

# Dieselbe Idee fuer Anleitungen: deren Namen duerfen keine Klammern enthalten,
# also ein Praefix. Ein Fall, der eine Anleitung anlegt, MUSS diesen Namen
# vorgeben — sonst bleibt sie nach dem Lauf in der Firma liegen.
ANL_MARKE = "eval-"

# Zustaende, in denen ein Auftrag nicht mehr von allein weiterlaeuft. Auf einen
# davon wird gewartet; alles andere heisst "noch beschaeftigt".
ENDE = ("fertig", "abgebrochen", "wartet_auf_kevin")

STD_TIMEOUT = 600         # Sekunden pro Fall, wenn die Datei nichts sagt
POLL = 2.0                # so oft wird nach dem Zustand gesehen

# PROTOCOL.md macht die Kuerze zur harten Regel ("hoechstens 10 Zeilen, ungefaehr
# 1000 Zeichen"). Weil das eine Zahl ist, prueft sie jeder Fall gratis mit —
# Geschwaetzigkeit im Bus ist der Verfall, der sonst niemandem auffaellt, bis
# wieder Berichte statt Ergebnisse gelesen werden. Pro Fall mit `max_nachricht: 0`
# abschaltbar.
STD_MAX_NACHRICHT = 1000


# ---------- Verbindung zur Firma ----------
def basis() -> str:
    return f"http://127.0.0.1:{PORT}"


def _auth_header() -> dict:
    """Basic-Auth nur, wenn ein Passwort gesetzt ist — genau wie im Server."""
    pw = os.environ.get("MATRIX_PASS", "")
    if not pw:
        return {}
    user = os.environ.get("MATRIX_USER", "Cody")
    return {"Authorization": "Basic " + b64encode(f"{user}:{pw}".encode()).decode()}


def api(pfad: str, daten=None, methode="", timeout=30):
    """Ein Aufruf gegen die laufende Firma. Wirft bei allem, was nicht 2xx ist."""
    url = basis() + pfad
    body = json.dumps(daten).encode() if daten is not None else None
    kopf = {"Content-Type": "application/json"} | _auth_header()
    req = urllib.request.Request(url, data=body, headers=kopf,
                                 method=methode or ("POST" if body else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        roh = r.read().decode("utf-8")
    return json.loads(roh) if roh.strip() else {}


def laeuft() -> bool:
    try:
        api("/api/version", timeout=5)
        return True
    except Exception:
        return False


def server_starten():
    """CONSTRUCT mit der Pruefstands-Firma hochfahren, wenn keine Instanz da ist.

    Direkt app.py mit dem venv-Python, nicht start.sh: start.sh oeffnet je nach
    Rechner ein Desktop-Fenster (desktop.py), und ein Pruefstand, der Fenster
    aufmacht, laesst sich nicht unbeaufsichtigt laufen.

    Eigener Port und eigene Firma (CONSTRUCT_FIRMA_DIR), Team-Modus per
    CONSTRUCT_TEAM erzwungen: die laufende Installation bleibt unberuehrt.

    Rueckgabe: der Prozess (dann muss der Aufrufer ihn beenden) oder None,
    wenn schon eine Instanz auf dem Port lief — die gehoert dann dem Aufrufer.
    """
    if laeuft():
        return None
    venvs = sorted(BASE_DIR.glob(".venv-*/bin/python"))
    py = str(venvs[0]) if venvs else sys.executable
    print(f"» keine Instanz auf {basis()} — starte eine ({Path(py).parent.parent.name})")
    # Das Serverlog MITSCHREIBEN, nicht wegwerfen. Als es nach DEVNULL ging,
    # fiel Fall 06 einmal durch und es war hinterher nicht mehr zu klaeren, ob
    # der Agent den Bus-Aufruf vergessen hatte oder der Lauf an einem
    # ueberlasteten API-Endpunkt abgebrochen war — zwei Befunde, die
    # entgegengesetzte Konsequenzen haben und im Ergebnis gleich aussehen.
    LAEUFE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LAEUFE_DIR / "server.log", "w", encoding="utf-8")
    FIRMA_DIR.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "MATRIX_PORT": str(PORT), "CONSTRUCT_FIRMA_DIR": str(FIRMA_DIR),
           "CONSTRUCT_TEAM": "1"}
    p = subprocess.Popen([py, str(BASE_DIR / "app.py")], cwd=str(BASE_DIR), env=env,
                         stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL)
    print(f"» Serverlog: {LAEUFE_DIR / 'server.log'}")
    # Grosszuegig: beim ersten Start prueft updates.py, ob Claude Code aktuell
    # ist, und das kann eine Minute dauern.
    for _ in range(120):
        if p.poll() is not None:
            raise SystemExit("!! CONSTRUCT ist beim Start abgebrochen. Das Serverlog "
                             "zeigt warum.")
        if laeuft():
            print("» Instanz ist da.")
            return p
        time.sleep(1)
    p.terminate()
    raise SystemExit("!! CONSTRUCT antwortet nach 120 s nicht.")


# ---------- Faelle ----------
def _split_frontmatter(txt: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", txt, re.S)
    return (m.group(1), m.group(2)) if m else ("", txt)


def _fm(fm: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", fm, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def _liste(v: str) -> list:
    return [x.strip() for x in str(v).split(",") if x.strip()]


def _zahl(v: str, fallback):
    try:
        return type(fallback)(v)
    except (TypeError, ValueError):
        return fallback


def fall_lesen(p: Path) -> dict:
    fm, brief = _split_frontmatter(p.read_text(encoding="utf-8"))
    return {
        "name": p.stem,
        "datei": str(p),
        "titel": _fm(fm, "titel") or p.stem,
        "brief": brief.strip(),
        "owner": _fm(fm, "owner") or "chef",
        # --- Soll-Werte. Was nicht dasteht, wird nicht geprueft. ---
        "erwartet": _fm(fm, "erwartet") or "fertig",
        "bremse": _fm(fm, "bremse"),           # "keine", ein Bremsenname, oder leer
        "max_hops": _zahl(_fm(fm, "max_hops"), 0),
        "max_kosten": _zahl(_fm(fm, "max_kosten"), 0.0),
        "max_nachricht": _zahl(_fm(fm, "max_nachricht"), STD_MAX_NACHRICHT),
        "timeout": _zahl(_fm(fm, "timeout"), STD_TIMEOUT),
        "dateien": _liste(_fm(fm, "dateien")),     # muessen auf der Platte liegen
        "gemeldet": _liste(_fm(fm, "gemeldet")),   # muessen im Feld `dateien` genannt sein
        "enthaelt": _liste(_fm(fm, "enthaelt")),
        "enthaelt_nicht": _liste(_fm(fm, "enthaelt_nicht")),
        "agenten": _liste(_fm(fm, "agenten")),
        # mindestens EINER davon muss dabei gewesen sein — fuer Regeln, bei
        # denen die Geschaeftsfuehrung zwischen mehreren Pruefern waehlen darf
        "agenten_einer": _liste(_fm(fm, "agenten_einer")),
    }


def faelle(muster: str = "", ordner: str = "faelle") -> list:
    d = PS_DIR / ordner
    if not d.is_dir():
        return []
    out = [fall_lesen(p) for p in sorted(d.glob("*.md"))]
    out = [f for f in out if f["brief"]]
    if muster:
        out = [f for f in out if muster.lower() in f["name"].lower()]
    return out


# ---------- Pruefen ----------
def _pruefung(name: str, ok, ist, soll) -> dict:
    """ok=True bestanden, ok=False durchgefallen, ok=None nicht messbar.

    Der dritte Zustand ist wichtiger, als er aussieht: eine Groesse, die gar
    nicht ankommt, darf nicht als bestanden durchgehen. Sonst steht da "kosten
    <= 0.40 OK", weil gemessene 0.00 nun mal kleiner ist als 0.40 — und der
    Pruefstand meldet gruen, waehrend er nichts prueft.
    """
    return {"was": name, "ok": None if ok is None else bool(ok), "ist": ist, "soll": soll}


def pruefen(fall: dict, t: dict, verlauf: list, arbeit: Path) -> list:
    """Die Soll-Ist-Vergleiche eines Falls. Reine Rechnerei, kein Modell."""
    p = []
    ist_status = t.get("status", "?")
    p.append(_pruefung("status", ist_status == fall["erwartet"],
                       ist_status, fall["erwartet"]))

    if fall["bremse"]:
        gefallen = ((t.get("eskalation") or {}).get("bremse") or "keine")
        p.append(_pruefung("bremse", gefallen == fall["bremse"], gefallen, fall["bremse"]))

    v = t.get("verbraucht") or {}
    if fall["max_hops"]:
        hops = int(v.get("hops") or 0)
        p.append(_pruefung("hops", hops <= fall["max_hops"], hops, f"<= {fall['max_hops']}"))
    if fall["max_kosten"]:
        kosten = round(float(v.get("cost") or 0), 4)
        # Es gab Zuege, aber keine Geldzahl: dann ist etwas schiefgelaufen
        # (Lauf abgebrochen, Schlussbuchung nicht angekommen) — das darf nicht
        # als bestanden durchgehen, nur weil 0.00 kleiner ist als jede Grenze.
        gemessen = kosten > 0 or not int(v.get("hops") or 0)
        p.append(_pruefung("kosten", (kosten <= fall["max_kosten"]) if gemessen else None,
                           f"{kosten:.4f}" if gemessen else "keine Zahl angekommen",
                           f"<= {fall['max_kosten']:.2f}"))

    for rel in fall["dateien"]:
        # Absolute Pfade waeren ein Fall, der aus seinem Ordner ausbricht — das
        # ist nie gemeint und wird als Fehler gezeigt, nicht still gefolgt.
        ziel = arbeit / rel
        drin = str(ziel.resolve()).startswith(str(arbeit.resolve()))
        p.append(_pruefung(f"datei {rel}", drin and ziel.exists(),
                           "da" if (drin and ziel.exists()) else
                           ("ausserhalb" if not drin else "fehlt"), "da"))

    # Dass eine Datei DA ist, heisst noch nicht, dass sie gemeldet wurde.
    # PROTOCOL.md verlangt sie im Feld `dateien` statt im Fliesstext — nur so
    # landet sie in den Artefakten und in den Personalakten der Beteiligten.
    if fall["gemeldet"]:
        genannt = {Path(str(a.get("pfad") or "")).name
                   for a in (t.get("artefakte") or [])}
        for rel in fall["gemeldet"]:
            n = Path(rel).name
            p.append(_pruefung(f"{rel} als Artefakt gemeldet", n in genannt,
                               "ja" if n in genannt else "nein", "ja"))

    if fall["enthaelt"] or fall["enthaelt_nicht"]:
        text = str(t.get("ergebnis") or "").lower()
        for wort in fall["enthaelt"]:
            p.append(_pruefung(f"ergebnis nennt {wort!r}", wort.lower() in text,
                               "ja" if wort.lower() in text else "nein", "ja"))
        # Die Gegenrichtung: HAUSSTIL.md verbietet Dinge (gendern, Floskeln),
        # und ein Verbot laesst sich nur pruefen, indem man nachsieht, dass es
        # NICHT dasteht.
        for wort in fall["enthaelt_nicht"]:
            drin = wort.lower() in text
            p.append(_pruefung(f"ergebnis meidet {wort!r}", not drin,
                               "steht drin" if drin else "nein", "nein"))

    if fall["agenten"]:
        dabei = beteiligte(verlauf)
        for slug in fall["agenten"]:
            p.append(_pruefung(f"{slug} war beteiligt", slug in dabei,
                               "ja" if slug in dabei else "nein", "ja"))

    if fall["agenten_einer"]:
        dabei = beteiligte(verlauf)
        treffer = [s for s in fall["agenten_einer"] if s in dabei]
        p.append(_pruefung("einer von " + "/".join(fall["agenten_einer"]) + " war beteiligt",
                           bool(treffer), ", ".join(treffer) or "niemand", "ja"))

    if fall["max_nachricht"]:
        laengste, von = 0, ""
        for e in verlauf:
            # Kevins eigener Auftragstext zaehlt nicht — den hat der Fall
            # geschrieben, nicht die Firma. System-Eintraege auch nicht.
            if e.get("von") in ("", "kevin", None) or e.get("art") == "system":
                continue
            n = len(str(e.get("text") or ""))
            if n > laengste:
                laengste, von = n, e.get("von") or "?"
        p.append(_pruefung("laengste Bus-Nachricht", laengste <= fall["max_nachricht"],
                           f"{laengste} Zeichen ({von})", f"<= {fall['max_nachricht']}"))
    return p


def beteiligte(verlauf: list) -> set:
    out = set()
    for e in verlauf:
        for wer in (e.get("von"), e.get("an")):
            if wer and wer != "kevin":
                out.add(wer)
    return out


# ---------- Einen Fall laufen lassen ----------
def arbeitsordner(fall: dict) -> Path:
    """Frischer, leerer Ordner pro Fall.

    Leer geraeumt, weil ein Fall sonst besteht, weil die Datei vom letzten Mal
    noch dalag — der unangenehmste falsche Positive, den ein Pruefstand haben
    kann.
    """
    d = ARBEIT_DIR / fall["name"]
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


NACHFASSEN_MAX = 20       # Sekunden, die auf die Schlussbuchung gewartet wird


def nachfassen(tid: str, t: dict, verlauf: list):
    """Auf die Schlussbuchung warten, bevor gemessen wird.

    Der Auftrag ist "fertig", sobald jemand `liefern` aufruft — das setzt der
    Bus-Handler mitten im laufenden Zug. Die KOSTEN bucht app.py aber erst in
    `_ende`, wenn der claude-Prozess wirklich beendet ist, und dazwischen
    liegen ein paar Sekunden.

    Gemessen wurde vorher im Moment des Statuswechsels, und damit kam derselbe
    Fall einmal mit 0.0000 $ und einmal mit 0.1139 $ heraus — je nachdem, ob
    der Poll vor oder nach der Buchung lag. Eine Zahl, die ohne Zutun
    schwankt, macht jeden Lauf-Vergleich wertlos: sie meldet Rueckschritte,
    die es nicht gibt.

    Gewartet wird, bis kein Zug mehr laeuft UND die Kosten sich zwischen zwei
    Abfragen nicht mehr aendern.
    """
    ende = time.time() + NACHFASSEN_MAX
    vorher = None
    while time.time() < ende:
        kosten = round(float((t.get("verbraucht") or {}).get("cost") or 0), 4)
        if not t.get("in_arbeit") and kosten == vorher:
            break
        vorher = kosten
        time.sleep(POLL)
        try:
            d = api(f"/api/team/auftraege/{tid}")
        except Exception:
            break
        t, verlauf = d.get("ticket") or t, d.get("verlauf") or verlauf
    return t, verlauf


def einen_lauf(fall: dict) -> dict:
    arbeit = arbeitsordner(fall)
    start = time.time()
    antwort = api("/api/team/auftraege", {"titel": f"{MARKE} {fall['titel']}",
                                   "brief": fall["brief"],
                                   "owner": fall["owner"],
                                   "cwd": str(arbeit)})
    tid = antwort["ticket"]["id"]

    t, verlauf, abbruch = {}, [], ""
    while True:
        time.sleep(POLL)
        try:
            d = api(f"/api/team/auftraege/{tid}")
        except Exception as e:
            abbruch = f"Firma nicht erreichbar: {type(e).__name__}"
            break
        t, verlauf = d.get("ticket") or {}, d.get("verlauf") or []
        if t.get("status") in ENDE:
            t, verlauf = nachfassen(tid, t, verlauf)
            break
        if time.time() - start > fall["timeout"]:
            abbruch = f"Zeit ueberschritten ({fall['timeout']} s)"
            # Den laufenden Zug abwuergen, den Auftrag aber STEHEN lassen: er
            # wuerde sonst weiter Geld ausgeben, waehrend der naechste Fall
            # schon laeuft — und geloescht koennte Kevin nicht mehr nachsehen,
            # woran der Fall haengengeblieben ist. Wegraeumen tut `aufraeumen`.
            rid = (t.get("in_arbeit") or {}).get("run_id") or ""
            if rid:
                try:
                    api(f"/api/stop/{rid}", methode="POST")
                except Exception:
                    pass
            break

    dauer = round(time.time() - start, 1)
    v = t.get("verbraucht") or {}
    ergebnis = {
        "fall": fall["name"],
        "ticket": tid,
        "dauer": dauer,
        "status": t.get("status", "?"),
        "hops": int(v.get("hops") or 0),
        "kosten": round(float(v.get("cost") or 0), 4),
        "schritte": len(verlauf),
        # Zwischenspeicher-Kennzahlen. Bewusst KEINE Pruefung mit Grenzwert:
        # sie schwanken mit der Laufzeit (der Zwischenspeicher laeuft nach
        # Minuten ab), und ein Fall, der wegen eines kalten Speichers rot wird,
        # erzieht nur dazu, den Pruefstand zu ignorieren. Fuer den Vergleich
        # zweier Laeufe taugen sie trotzdem — darum stehen sie im Bericht.
        "cache_read": int(v.get("cache_read") or 0),
        "cache_write": int(v.get("cache_write") or 0),
        "frisch": int(v.get("frisch") or 0),
        "agenten": sorted(beteiligte(verlauf)),
        "artefakte": [a.get("pfad") for a in (t.get("artefakte") or [])],
        "bremse": (t.get("eskalation") or {}).get("bremse") or "",
        "abbruch": abbruch,
        "pruefungen": [] if abbruch else pruefen(fall, t, verlauf, arbeit),
    }
    # Nicht messbar (ok=None) laesst den Fall nicht durchfallen — es waere
    # unehrlich, einen sauberen Lauf rot zu faerben, weil eine Zahl fehlt. Der
    # Bericht sagt es stattdessen ausdruecklich an.
    ergebnis["bestanden"] = (not abbruch) and all(x["ok"] is not False
                                                  for x in ergebnis["pruefungen"])
    return ergebnis


# ---------- Ausgabe ----------
def _zeile(e: dict) -> str:
    zeichen = "OK  " if e["bestanden"] else "FEHL"
    kopf = (f"{zeichen} {e['fall']:<24} {e['status']:<22} "
            f"{e['hops']:>2} Zuege  {e['kosten']:>7.4f} $  {e['dauer']:>6.1f} s")
    if e["abbruch"]:
        return kopf + f"\n       ! {e['abbruch']}"
    for p in e["pruefungen"]:
        if p["ok"] is False:
            kopf += f"\n       - {p['was']}: ist {p['ist']}, soll {p['soll']}"
        elif p["ok"] is None:
            kopf += f"\n       ? {p['was']}: {p['ist']} — nicht geprueft"
    return kopf


def bericht(lauf: dict):
    print()
    for e in lauf["faelle"]:
        print(_zeile(e))
    n, ok = len(lauf["faelle"]), sum(1 for e in lauf["faelle"] if e["bestanden"])
    print(f"\n{ok}/{n} bestanden · {lauf['kosten']:.4f} $ · {lauf['dauer']:.0f} s")
    gelesen = sum(e.get("cache_read", 0) for e in lauf["faelle"])
    neu = sum(e.get("cache_write", 0) for e in lauf["faelle"])
    frisch = sum(e.get("frisch", 0) for e in lauf["faelle"])
    if gelesen or neu or frisch:
        ges = gelesen + neu + frisch
        print(f"Zwischenspeicher: {gelesen:>8} gelesen · {neu:>7} geschrieben · "
              f"{frisch:>6} frisch  ({100*gelesen/ges:.0f} % aus dem Speicher)")
    if lauf["kosten"] == 0 and any(e["hops"] for e in lauf["faelle"]):
        print("Hinweis: es gab Zuege, aber keine Kostenzahl. Da stimmt etwas "
              "nicht — normalerweise bucht der Server sie beim Zugende.")


def letzte_laeufe(n: int = 2) -> list:
    if not LAEUFE_DIR.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(LAEUFE_DIR.glob("*.json"))[-n:]]


def vergleich(alt: dict, neu: dict):
    """Was sich seit dem letzten Mal geaendert hat — nur das.

    Das ist der eigentliche Zweck des Pruefstands: nicht "besteht der Fall",
    sondern "besteht er noch, seit ich PROTOCOL.md angefasst habe".
    """
    a = {e["fall"]: e for e in alt["faelle"]}
    b = {e["fall"]: e for e in neu["faelle"]}
    zeilen = []
    for name, e in b.items():
        v = a.get(name)
        if not v:
            zeilen.append(f"  + {name}: neu ({'bestanden' if e['bestanden'] else 'durchgefallen'})")
            continue
        if v["bestanden"] and not e["bestanden"]:
            zeilen.append(f"  ! {name}: RUECKSCHRITT — bestand vorher, jetzt nicht mehr")
        elif e["bestanden"] and not v["bestanden"]:
            zeilen.append(f"  + {name}: repariert")
        dk, dh = e["kosten"] - v["kosten"], e["hops"] - v["hops"]
        if abs(dk) >= 0.02 or dh:
            zeilen.append(f"    {name}: {dh:+d} Zuege, {dk:+.4f} $")
    for name in a:
        if name not in b:
            zeilen.append(f"  - {name}: nicht mitgelaufen")
    print(f"\nGegen {alt['stempel']}:")
    print("\n".join(zeilen) if zeilen else "  nichts Nennenswertes geaendert.")


# ---------- Kommandos ----------
def cmd_liste(args):
    fs = faelle(args.nur, args.faelle)
    if not fs:
        return print(f"Keine Faelle in {PS_DIR / args.faelle}.")
    for f in fs:
        soll = [f"status={f['erwartet']}"]
        if f["bremse"]:
            soll.append(f"bremse={f['bremse']}")
        if f["max_hops"]:
            soll.append(f"hops<={f['max_hops']}")
        if f["max_kosten"]:
            soll.append(f"kosten<={f['max_kosten']:.2f}")
        if f["dateien"]:
            soll.append("dateien=" + ",".join(f["dateien"]))
        if f["agenten"]:
            soll.append("agenten=" + ",".join(f["agenten"]))
        print(f"{f['name']:<24} {f['titel']}\n{'':<24} {' · '.join(soll)}")


def cmd_lauf(args):
    fs = faelle(args.nur, args.faelle)
    if not fs:
        raise SystemExit(f"!! Keine Faelle in {PS_DIR / args.faelle} (Muster: {args.nur or 'alle'}).")
    schaetzung = sum(f["max_kosten"] for f in fs)
    print(f"{len(fs)} Faelle, Obergrenze laut Faellen ~{schaetzung:.2f} $"
          + (f", Budget {args.budget:.2f} $" if args.budget else ""))

    eigener = server_starten()
    LAEUFE_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    lauf = {"stempel": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
            "faelle": [], "kosten": 0.0, "dauer": 0.0}
    try:
        for i, f in enumerate(fs, 1):
            print(f"[{i}/{len(fs)}] {f['name']} …", flush=True)
            e = einen_lauf(f)
            lauf["faelle"].append(e)
            lauf["kosten"] = round(lauf["kosten"] + e["kosten"], 4)
            print("      " + _zeile(e).strip())
            if args.budget and lauf["kosten"] >= args.budget:
                print(f"\n!! Budget erreicht ({lauf['kosten']:.4f} $) — Rest wird "
                      f"uebersprungen.")
                lauf["abgebrochen_bei"] = f["name"]
                break
    finally:
        lauf["dauer"] = round(time.time() - start, 1)
        if eigener:
            eigener.terminate()
        if lauf["faelle"]:
            ziel = LAEUFE_DIR / f"{lauf['stempel']}.json"
            ziel.write_text(json.dumps(lauf, indent=2, ensure_ascii=False), encoding="utf-8")
            bericht(lauf)
            vorher = letzte_laeufe(2)
            if len(vorher) == 2:
                vergleich(vorher[0], lauf)
            print(f"\n{ziel}")

    if any(not e["bestanden"] for e in lauf["faelle"]):
        raise SystemExit(1)


def cmd_vergleich(args):
    l = letzte_laeufe(2)
    if len(l) < 2:
        raise SystemExit("!! Es braucht zwei Laeufe zum Vergleichen.")
    bericht(l[1])
    vergleich(l[0], l[1])


def historie_bereinigen() -> int:
    """Testauftraege aus den Personalakten werfen.

    Seit der Server fuer markierte Auftraege keine Historie mehr schreibt, ist
    das nur noch fuer Altbestand — der aber steht im Systemprompt jedes
    Mitarbeiters und verdraengt dort echte Arbeit (MAX_HISTORIE Zeilen).
    """
    weg = 0
    for p in sorted((FIRMA_DIR / "agents").glob("*/HISTORIE.jsonl")):
        zeilen = p.read_text(encoding="utf-8", errors="replace").splitlines()
        bleibt = []
        for z in zeilen:
            try:
                titel = json.loads(z).get("titel", "")
            except ValueError:
                bleibt.append(z)
                continue
            if str(titel).startswith(MARKE):
                weg += 1
            else:
                bleibt.append(z)
        if len(bleibt) != len(zeilen):
            p.write_text("\n".join(bleibt) + ("\n" if bleibt else ""), encoding="utf-8")
    return weg


def cmd_aufraeumen(args):
    """Testauftraege und Arbeitsordner weg — der Ordner soll aussehen wie vorher.

    Zwei Wege, je nachdem ob die Firma laeuft: ueber die API, wenn sie
    antwortet (dann raeumt der Server auch seine Sperren und Feeds mit ab),
    sonst direkt auf der Platte. Der zweite Weg ist noetig, weil `lauf` die
    Instanz am Ende selbst wieder beendet — danach liefe `aufraeumen` sonst ins
    Leere und meldete trotzdem Vollzug.

    Angefasst wird ausschliesslich, was die Marke im Titel traegt. Kevins
    eigene Auftraege bleiben liegen, auch wenn sie abgebrochen sind.
    """
    weg = []
    if laeuft():
        try:
            for t in api("/api/team/auftraege").get("tickets", []):
                if str(t.get("titel", "")).startswith(MARKE):
                    api(f"/api/team/auftraege/{t['id']}", methode="DELETE")
                    weg.append(t["id"])
        except Exception as e:
            print(f"!! Auftraege nicht aufgeraeumt: {type(e).__name__}: {e}")
    else:
        tickets = FIRMA_DIR / "auftraege"
        for d in sorted(tickets.iterdir()) if tickets.is_dir() else []:
            f = d / "ticket.json"
            if not f.is_file():
                continue
            try:
                titel = json.loads(f.read_text(encoding="utf-8")).get("titel", "")
            except (ValueError, OSError):
                continue          # kaputte Akte ist nicht unsere — liegen lassen
            if titel.startswith(MARKE):
                shutil.rmtree(d, ignore_errors=True)
                weg.append(d.name)
    if ARBEIT_DIR.exists():
        shutil.rmtree(ARBEIT_DIR)
    # Anleitungen, die ein Fall angelegt hat. Sie tragen die Marke im NAMEN,
    # weil ein Fall sonst bei jedem Lauf eine weitere Anleitung in Kevins Firma
    # zuruecklaesst — der Pruefstand soll die Firma messen, nicht veraendern.
    anleitungen = 0
    d = FIRMA_DIR / "anleitungen"
    for p in sorted(d.glob(f"{ANL_MARKE}*")) if d.is_dir() else []:
        shutil.rmtree(p, ignore_errors=True)
        anleitungen += 1
    historie = historie_bereinigen()
    print(f"{len(weg)} Testauftraege geloescht, Arbeitsordner weg"
          + (f", {anleitungen} Test-Anleitungen weg" if anleitungen else "")
          + (f", {historie} Testzeilen aus den Personalakten" if historie else "") + ".")


def cmd_firma_vorbereiten(args):
    """Die Pruefstands-Firma mit einer bestehenden Belegschaft fuellen.

    Kopiert agents/ (ohne Gespraechszeiger und Zwischendateien), anleitungen/,
    USER.md und die Regelwerke (HAUSSTIL, PROTOCOL, GESTALTUNG, MODELS) — also genau
    das, woraus ein Systemprompt entsteht. Damit misst derselbe Fall dieselbe
    Belegschaft mit denselben Regeln: ein Unterschied zum frueheren Lauf kommt dann
    aus dem Programm, nicht aus den Daten.
    """
    quelle = Path(args.aus).expanduser().resolve()
    if not (quelle / "agents").is_dir():
        raise SystemExit(f"!! {quelle}/agents gibt es nicht.")
    if FIRMA_DIR.exists():
        shutil.rmtree(FIRMA_DIR)
    FIRMA_DIR.mkdir(parents=True)
    # HISTORIE.jsonl bleibt: sie steht im Systemprompt, ein Lauf ohne sie waere ein
    # anderer Prompt als der des Vergleichslaufs.
    ignorieren = shutil.ignore_patterns("chat.json", ".systemprompt", ".sysprompt-*", "*.tmp")
    shutil.copytree(quelle / "agents", FIRMA_DIR / "agents", ignore=ignorieren)
    if (quelle / "anleitungen").is_dir():
        shutil.copytree(quelle / "anleitungen", FIRMA_DIR / "anleitungen")
    for name in ("USER.md", "HAUSSTIL.md", "PROTOCOL.md", "GESTALTUNG.md", "MODELS.md"):
        if (quelle / name).is_file():
            shutil.copy2(quelle / name, FIRMA_DIR / name)
    n = len(list((FIRMA_DIR / "agents").glob("*/AGENT.md")))
    print(f"{n} Mitarbeiter und die Regelwerke aus {quelle} nach {FIRMA_DIR} kopiert.")


def main():
    ap = argparse.ArgumentParser(description="Pruefstand fuer die Firma in CONSTRUCT")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("lauf", help="Faelle durchlaufen und messen")
    p.add_argument("--nur", default="", help="nur Faelle, deren Name das enthaelt")
    p.add_argument("--budget", type=float, default=0.0,
                   help="abbrechen, sobald so viel Dollar verbraucht sind")
    p.add_argument("--faelle", default="faelle",
                   help="Ordner unter scripts/pruefstand/ (Vorgabe: faelle; "
                        "oder ein eigener Ordner faelle-<name>)")
    p.set_defaults(fn=cmd_lauf)

    p = sub.add_parser("liste", help="vorhandene Faelle zeigen")
    p.add_argument("--nur", default="")
    p.add_argument("--faelle", default="faelle")
    p.set_defaults(fn=cmd_liste)

    p = sub.add_parser("firma-vorbereiten",
                       help="Belegschaft einer bestehenden Firma (FACTORIA) in die Pruefstands-Firma kopieren")
    p.add_argument("--aus", required=True, help="Ordner mit agents/, anleitungen/, HAUSSTIL.md …")
    p.set_defaults(fn=cmd_firma_vorbereiten)

    p = sub.add_parser("vergleich", help="letzten Lauf gegen den davor")
    p.set_defaults(fn=cmd_vergleich)

    p = sub.add_parser("aufraeumen", help="Testauftraege und Arbeitsordner loeschen")
    p.set_defaults(fn=cmd_aufraeumen)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
