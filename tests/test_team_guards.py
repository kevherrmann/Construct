"""Unittests fuer die Bremsen — die einzige Logik hier, die ohne Modell prueft.

    python -m pytest tests/test_team_guards.py

Der Pruefstand (scripts/pruefstand.py) misst die ganze Firma und kostet Geld;
das hier kostet nichts und faengt die Faelle, die am 04.09.2026 als falsche
Alarme aufgefallen sind.
"""
import time
import unittest

from server.team import auftraege as tickets
from server.team import guards


def _v(*schritte):
    now = time.time() - 3600      # in der Vergangenheit: freigeben() setzt frei_seit auf jetzt
    out = []
    for i, (von, an, art) in enumerate(schritte):
        out.append({"id": f"m{i}", "von": von, "an": an, "art": art,
                    "text": f"{art} {i}", "ts": now + i})
    return out


def _t(ohne_artefakt=0):
    return {"wache": {"ohne_artefakt": ohne_artefakt, "frei_seit": 0}}


class Bremsen(unittest.TestCase):
    def test_rueckfragen_sind_kein_pingpong(self):
        v = _v(("kevin", "lumina", "auftrag"), ("lumina", "luna", "auftrag"),
               ("luna", "lumina", "frage"), ("lumina", "luna", "antwort"),
               ("luna", "lumina", "frage"), ("lumina", "luna", "antwort"),
               ("luna", "lumina", "frage"), ("lumina", "luna", "antwort"))
        self.assertEqual(guards.pruefe_nach_zug(_t(), v)[0], None)

    def test_gegenseitiges_fragen_ist_pingpong(self):
        v = _v(("lumina", "luna", "auftrag"),
               ("luna", "lumina", "frage"), ("lumina", "luna", "frage"),
               ("luna", "lumina", "frage"), ("lumina", "luna", "frage"),
               ("luna", "lumina", "frage"), ("lumina", "luna", "frage"))
        self.assertEqual(guards.pruefe_nach_zug(_t(), v)[0], "pingpong")

    def test_nachbesserung_mit_ergebnissen_ist_fortschritt(self):
        v = _v(("lumina", "luna", "auftrag"), ("luna", "lumina", "ergebnis"),
               ("lumina", "luna", "auftrag"), ("luna", "lumina", "ergebnis"),
               ("lumina", "luna", "auftrag"), ("luna", "lumina", "ergebnis"))
        self.assertEqual(guards.pruefe_nach_zug(_t(), v)[0], None)

    def test_einwurf_zaehlt_nicht_als_schritt(self):
        v = _v(("kevin", "luna", "einwurf"), ("lumina", "luna", "auftrag"))
        self.assertEqual(len(guards.geroutet(_t(), v)), 1)

    def test_wiederholung(self):
        v = _v(("lumina", "luna", "auftrag"), ("luna", "lumina", "frage"),
               ("lumina", "luna", "antwort"), ("luna", "lumina", "frage"))
        v[1]["text"] = v[3]["text"] = "Welchen Port soll ich nehmen, 8000 oder 8080?"
        self.assertEqual(guards.pruefe_nach_zug(_t(), v)[0], "wiederholung")

    def test_kein_fortschritt_erst_ab_grenze(self):
        v = _v(("lumina", "luna", "auftrag"), ("luna", "lumina", "ergebnis"))
        self.assertEqual(guards.pruefe_nach_zug(_t(guards.OHNE_ARTEFAKT_MAX - 1), v)[0], None)
        self.assertEqual(guards.pruefe_nach_zug(_t(guards.OHNE_ARTEFAKT_MAX), v)[0],
                         "kein_fortschritt")

    def test_freigeben_setzt_zaehlung_zurueck(self):
        t = _t(5)
        v = _v(*[("lumina", "luna", "auftrag"), ("luna", "lumina", "ergebnis")] * 6)
        self.assertEqual(guards.pruefe(t, {"von": "lumina", "an": "luna"}, v)[0], "hin_und_her")
        guards.freigeben(t)
        self.assertEqual(guards.pruefe(t, {"von": "lumina", "an": "luna"}, v)[0], None)
        self.assertEqual(t["wache"]["ohne_artefakt"], 0)


class Kleinauftrag(unittest.TestCase):
    """Wann `liefern` am Verteiler vorbei direkt zu Kevin darf (15.09.2026)."""

    def _k(self, *schritte):
        v = _v(*[(von, an, art) for von, an, art, _ in schritte])
        for e, (_, _, _, groesse) in zip(v, schritte):
            if groesse:
                e["groesse"] = groesse
        return v

    def test_klein_und_allein_geht_direkt(self):
        v = self._k(("kevin", "lumina", "auftrag", ""), ("lumina", "luna", "auftrag", "klein"))
        self.assertTrue(tickets.kleinauftrag_direkt(v, "luna", "lumina"))

    def test_ohne_groesse_bleibt_es_bei_der_geschaeftsfuehrung(self):
        v = self._k(("kevin", "lumina", "auftrag", ""), ("lumina", "luna", "auftrag", "normal"))
        self.assertFalse(tickets.kleinauftrag_direkt(v, "luna", "lumina"))
        v = self._k(("kevin", "lumina", "auftrag", ""), ("lumina", "luna", "auftrag", ""))
        self.assertFalse(tickets.kleinauftrag_direkt(v, "luna", "lumina"))

    def test_zwei_parallel_vergeben_ist_nicht_klein(self):
        # Sonst schloesse Elaras Ergebnis den Auftrag, waehrend Codys nur bei Luna liegt.
        v = self._k(("kevin", "lumina", "auftrag", ""),
                    ("lumina", "luna", "auftrag", "klein"),
                    ("lumina", "css-spezialist", "auftrag", "klein"))
        self.assertFalse(tickets.kleinauftrag_direkt(v, "luna", "lumina"))
        self.assertFalse(tickets.kleinauftrag_direkt(v, "css-spezialist", "lumina"))

    def test_nachgeplanter_pruefer_hebt_klein_auf(self):
        v = self._k(("kevin", "lumina", "auftrag", ""),
                    ("lumina", "luna", "auftrag", "klein"),
                    ("luna", "lumina", "ergebnis", ""),
                    ("lumina", "qa", "auftrag", "klein"))
        self.assertFalse(tickets.kleinauftrag_direkt(v, "qa", "lumina"))

    def test_kevins_antwort_auf_rueckfrage_bricht_klein_nicht(self):
        v = self._k(("kevin", "lumina", "auftrag", ""),
                    ("lumina", "luna", "auftrag", "klein"),
                    ("kevin", "luna", "antwort", ""))
        self.assertTrue(tickets.kleinauftrag_direkt(v, "luna", "lumina"))

    def test_kevins_neuer_auftrag_setzt_zurueck(self):
        # Einwurf als AUFTRAG an Luna: danach zaehlt nur, was sie neu vergibt.
        v = self._k(("kevin", "lumina", "auftrag", ""),
                    ("lumina", "luna", "auftrag", "klein"),
                    ("kevin", "lumina", "auftrag", ""),
                    ("lumina", "css-spezialist", "auftrag", "klein"))
        self.assertFalse(tickets.kleinauftrag_direkt(v, "luna", "lumina"))
        self.assertTrue(tickets.kleinauftrag_direkt(v, "css-spezialist", "lumina"))

    def test_nur_der_beauftragte_selbst(self):
        v = self._k(("kevin", "lumina", "auftrag", ""), ("lumina", "luna", "auftrag", "klein"),
                    ("luna", "qa", "auftrag", "klein"))
        # Codys Unterauftrag an Miranda ist kein Kleinauftrag der Geschaeftsfuehrung.
        self.assertFalse(tickets.kleinauftrag_direkt(v, "qa", "lumina"))
        self.assertTrue(tickets.kleinauftrag_direkt(v, "luna", "lumina"))


if __name__ == "__main__":
    unittest.main()
