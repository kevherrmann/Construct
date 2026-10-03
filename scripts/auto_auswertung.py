#!/usr/bin/env python3
"""Auswertung des Schattenbetriebs der automatischen Modellwahl (auto_modell.py).

    python3 scripts/auto_auswertung.py [--alle]

Legt je Session den Vorschlag neben das, was wirklich lief: Modell, Schritte,
Dauer, Ausgabe-Tokens. Große Sessions, für die nur Haiku/Sonnet vorgeschlagen
war, sind die Kandidaten für Fehlentscheidungen — die schauen wir uns an.
"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from server.core import PROJECTS_DIR  # noqa: E402
from server.auto_modell import LOG  # noqa: E402

STUFE = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}


def familie(model_id: str) -> str:
    for f in STUFE:
        if f in (model_id or ""):
            return f
    return model_id or "?"


def verlauf(sid: str) -> dict:
    """Was in der Session wirklich passiert ist (aus dem Transkript)."""
    f = next(iter(PROJECTS_DIR.glob(f"*/{sid}.jsonl")), None) if sid else None
    if not f:
        return {}
    seen, modelle, schritte, out_tok, ts = set(), Counter(), 0, 0, []
    for line in f.open(encoding="utf-8", errors="replace"):
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("timestamp"):
            ts.append(ev["timestamp"])
        if ev.get("type") != "assistant":
            continue
        m = ev.get("message") or {}
        key = (m.get("id"), ev.get("requestId"))
        if not m.get("id") or key in seen or m.get("model") == "<synthetic>":
            continue
        seen.add(key)
        schritte += 1
        modelle[familie(m.get("model", ""))] += 1
        out_tok += (m.get("usage") or {}).get("output_tokens", 0)
    dauer = 0.0
    if len(ts) > 1:
        a = datetime.fromisoformat(min(ts).replace("Z", "+00:00"))
        b = datetime.fromisoformat(max(ts).replace("Z", "+00:00"))
        dauer = (b - a).total_seconds() / 60
    return {"modell": modelle.most_common(1)[0][0] if modelle else "?",
            "schritte": schritte, "out": out_tok, "minuten": dauer}


def main():
    if not LOG.exists():
        print(f"Noch keine Daten ({LOG.name} fehlt). Schattenbetrieb an? settings.json → auto.schatten")
        return
    rows = [json.loads(z) for z in LOG.read_text(encoding="utf-8").splitlines() if z.strip()]
    print(f"{len(rows)} Sessions im Protokoll, {rows[0]['ts'][:10]} bis {rows[-1]['ts'][:10]}\n")
    print(f"{'Datum':16} {'lief':7} {'Vorschl.':8} {'sicher':6} {'Schr.':>5} {'Min':>5} {'Out-Tok':>8}  Nachricht / Grund")
    zaehl, verdacht, fehler = Counter(), [], 0
    for r in rows:
        if r.get("fehler"):
            fehler += 1
            continue
        v = verlauf(r.get("session_id"))
        lief = v.get("modell") or familie(r.get("gewaehlt"))
        vor = r.get("vorschlag") or "?"
        zaehl[(lief, vor)] += 1
        # Verdacht: Vorschlag schwächer als gelaufen UND die Session war groß.
        gross = v.get("schritte", 0) >= 15 or v.get("minuten", 0) >= 20
        kleiner = STUFE.get(vor, 9) < STUFE.get(lief, 9)
        mark = "⚠" if (kleiner and gross) else " "
        if mark == "⚠":
            verdacht.append(r)
        sicher = f"{r['sicherheit']:.2f}" if isinstance(r.get("sicherheit"), (int, float)) else " - "
        print(f"{r['ts'][:16]:16} {lief:7} {vor:8} {sicher:6} {v.get('schritte', 0):5} "
              f"{v.get('minuten', 0):5.0f} {v.get('out', 0):8}{mark} {r['nachricht'][:60]!r}"
              + (f"  ← {r['grund']}" if "--alle" in sys.argv else ""))
    gesamt = sum(zaehl.values())
    gleich = sum(n for (a, b), n in zaehl.items() if a == b)
    print(f"\nÜbereinstimmung mit dem tatsächlich genutzten Modell: {gleich}/{gesamt}"
          + (f" ({gleich / gesamt:.0%})" if gesamt else ""))
    print("Vorschläge:", dict(Counter(r.get("vorschlag") for r in rows if not r.get("fehler"))))
    print(f"Verdacht auf Fehlentscheidung (schwächer vorgeschlagen, Session groß): {len(verdacht)}")
    if fehler:
        print(f"Klassifizierer ohne Ergebnis: {fehler}")


if __name__ == "__main__":
    main()
