"""WCAG-Kontrast zweier Farben — als Bus-Werkzeug fuer die Gestalter.

Warum ein Werkzeug und keine Kopfrechnung: die Formel hat eine Gamma-Kurve
mit Fallunterscheidung, und ein Sprachmodell schaetzt "#ccc auf #333" gern
auf "etwa 10:1" — es sind 7,87:1; bei "#777 auf #fff" schaetzt es "reicht"
und es sind 4,48:1, also knapp NICHT AA. GESTALTUNG.md verlangt 4,5:1 fuer
Text und 3:1 fuer Bedienelemente; das hier ist die Messung dazu.

Farben: #rgb, #rrggbb, "r,g,b" oder rgb(r,g,b).
"""
import re

AA_TEXT = 4.5       # normaler Text
AA_GROSS = 3.0      # grosser Text (ab 24 px, oder 19 px fett) und Bedienelemente
AAA_TEXT = 7.0


class FarbFehler(ValueError):
    pass


def parse(farbe: str) -> tuple:
    s = str(farbe or "").strip().lower()
    m = re.fullmatch(r"#?([0-9a-f]{3}|[0-9a-f]{6})", s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"(?:rgb\()?\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)?", s)
    if m and all(0 <= int(x) <= 255 for x in m.groups()):
        return tuple(int(x) for x in m.groups())
    raise FarbFehler(f"'{farbe}' ist keine Farbe. Erlaubt: #rgb, #rrggbb, r,g,b oder rgb(r,g,b).")


def _linear(c: int) -> float:
    v = c / 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminanz(rgb: tuple) -> float:
    r, g, b = (_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def verhaeltnis(a: str, b: str) -> float:
    la, lb = luminanz(parse(a)), luminanz(parse(b))
    hell, dunkel = max(la, lb), min(la, lb)
    return (hell + 0.05) / (dunkel + 0.05)


def bericht(vorne: str, hinten: str) -> str:
    """Eine Zeile Zahl, eine Zeile Urteil — mehr braucht niemand."""
    q = verhaeltnis(vorne, hinten)
    urteil = []
    urteil.append("Text: " + ("AAA" if q >= AAA_TEXT else "AA" if q >= AA_TEXT else "FAELLT DURCH (min 4,5:1)"))
    urteil.append("grosser Text / Bedienelemente: " + ("ok" if q >= AA_GROSS else "FAELLT DURCH (min 3:1)"))
    return f"{vorne} auf {hinten}: {q:.2f}:1 — " + "; ".join(urteil)
