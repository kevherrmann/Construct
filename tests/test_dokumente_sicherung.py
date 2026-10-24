"""Sicherung der Dokumente: Ordner-Spiegel, verschlüsselter Server, Zurückholen."""
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from server.dokumente import ablage, ocr, sicherung
from server.sicherung import Fehler, krypto
from test_dokumente import pdf_mit_text


@pytest.fixture(autouse=True)
def daten(tmp_path, monkeypatch):
    from server import config as cfg
    monkeypatch.setattr(ablage, "DATEN", tmp_path / "dokumente")
    monkeypatch.setattr(ablage, "HINTERGRUND", False)
    monkeypatch.setattr(ocr, "verfuegbar", lambda: False)
    # scrypt in voller Stärke kostet je Ableitung spürbar Zeit
    monkeypatch.setattr(krypto, "N", 2 ** 10)
    (tmp_path / "settings.json").write_text(json.dumps({"lang": "de", "tiles": {"dokumente": True}}))
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")
    return tmp_path


def aufnehmen(tmp, name, zeilen):
    d = ablage.neu(pdf_mit_text(tmp / f"{name}.pdf", zeilen), titel=name)
    ablage.jetzt_lesen_alle()
    return d["id"]


class FakeServer:
    """Wie sftp.Server, aber ein Ordner auf der Platte."""
    def __init__(self, wurzel: Path):
        self.wurzel = wurzel
        self.aufrufe = 0

    def _o(self, u):
        return self.wurzel / u if u else self.wurzel

    def testen(self):
        self.wurzel.mkdir(parents=True, exist_ok=True)

    def liste(self, u=""):
        o = self._o(u)
        return {f.name for f in o.iterdir() if f.is_file()} if o.is_dir() else set()

    def hochladen(self, dateien, u=""):
        self.aufrufe += 1
        self._o(u).mkdir(parents=True, exist_ok=True)
        for quelle, name in dateien:
            shutil.copyfile(quelle, self._o(u) / name)

    def holen(self, dateien, u=""):
        for name, ziel in dateien:
            shutil.copyfile(self._o(u) / name, ziel)

    def loeschen(self, namen, u=""):
        for n in namen:
            (self._o(u) / n).unlink()


def test_ohne_ziel_nichts_eingerichtet(daten):
    aufnehmen(daten, "A", ["Text"])
    s = sicherung.stand()
    assert not s["eingerichtet"] and sicherung.faellig() == []


def test_ordner_muss_existieren(daten):
    with pytest.raises(Fehler):
        sicherung.einrichten({"ordner": str(daten / "gibtsnicht")})
    with pytest.raises(Fehler):
        sicherung.einrichten({"ordner": "relativ/pfad"})
    ablage.DATEN.mkdir(parents=True, exist_ok=True)
    with pytest.raises(Fehler):
        sicherung.einrichten({"ordner": str(ablage.DATEN)})


def test_ordner_spiegel_umbenennen_und_zurueckholen(daten):
    platte = daten / "platte"
    platte.mkdir()
    sicherung.einrichten({"ordner": str(platte)})
    a = aufnehmen(daten, "Brief", ["Stadtwerke", "Lengerich, 15.01.2026"])
    s = sicherung.sichern()
    assert s["ziele"]["ordner"]["aktuell"] and not s["ziele"]["ordner"]["fehler"]
    spiegel = platte / sicherung.UNTERORDNER
    alt = ablage.dokument(a)["datei"]
    assert (spiegel / alt).is_file() and (spiegel / "dokumente.db").is_file()

    # Umbenennen: neue Datei im Spiegel, alte nach _ersetzt statt gelöscht
    ablage.aendern(a, {"titel": "Jahresabrechnung", "absender": "Stadtwerke"})
    assert not sicherung.stand()["ziele"]["ordner"]["aktuell"]
    sicherung.sichern()
    neu = ablage.dokument(a)["datei"]
    assert (spiegel / neu).is_file() and not (spiegel / alt).exists()
    assert list((spiegel / "_ersetzt").rglob(Path(alt).name))

    r = sicherung.pruefen("ordner")
    assert r["fehlt_anzahl"] == 0 and r["dokumente"] == r["dokumente_soll"] == 1


def test_ordner_weg_meldet_fehler_statt_systemplatte(daten):
    platte = daten / "platte"
    platte.mkdir()
    sicherung.einrichten({"ordner": str(platte)})
    aufnehmen(daten, "A", ["x"])
    platte.rmdir()                                    # Platte abgezogen
    s = sicherung.sichern()
    assert "nicht da" in s["ziele"]["ordner"]["fehler"] and not platte.exists()


def test_server_verschluesselt_inkrementell_und_zurueck(daten, monkeypatch):
    fake = FakeServer(daten / "vps")
    monkeypatch.setattr(sicherung, "_server", lambda e: fake if (e.get("server") or {}).get("host") else None)
    sicherung.einrichten({"server": {"host": "beispiel.de"}, "kennwort": "geheim-genug"})
    a = aufnehmen(daten, "Bescheid", ["Finanzamt Ibbenbüren", "Grundsteuer 2023"])
    s = sicherung.sichern(["server"])
    assert s["ziele"]["server"]["aktuell"], s["ziele"]["server"]["fehler"]
    objekte = fake.liste("objekte")
    assert len(objekte) == 2                          # PDF + Datenbank
    # Auf dem Server steht kein Klartext
    for n in objekte:
        roh = (fake.wurzel / "objekte" / n).read_bytes()
        assert roh.startswith(krypto.MAGIC) and b"Grundsteuer" not in roh and b"%PDF" not in roh

    # Umbenennen lädt kein PDF neu, nur Datenbank und Stand
    ablage.aendern(a, {"titel": "Grundsteuer", "eingang": False})
    sicherung.sichern(["server"])
    assert len(fake.liste("objekte")) == 3

    r = sicherung.pruefen("server")
    assert r["fehlt_anzahl"] == 0 and r["dokumente"] == 1

    # Falsches Kennwort: kein Datenmüll, sondern eine klare Meldung
    sicherung.einrichten({"kennwort": "ganz-anderes-kw"})
    with pytest.raises(Fehler, match="Kennwort"):
        sicherung.wiederherstellen("server", daten / "zurueck")


def test_server_ohne_kennwort(daten, monkeypatch):
    fake = FakeServer(daten / "vps")
    monkeypatch.setattr(sicherung, "_server", lambda e: fake)
    sicherung.einrichten({"server": {"host": "beispiel.de"}})
    aufnehmen(daten, "A", ["x"])
    s = sicherung.sichern(["server"])
    assert "Kennwort" in s["ziele"]["server"]["fehler"]


def test_server_alte_staende_und_waisen_weg(daten, monkeypatch):
    fake = FakeServer(daten / "vps")
    monkeypatch.setattr(sicherung, "_server", lambda e: fake)
    monkeypatch.setattr(sicherung, "STAENDE_BEHALTEN", 2)
    sicherung.einrichten({"server": {"host": "beispiel.de"}, "kennwort": "geheim-genug"})
    a = aufnehmen(daten, "A", ["eins"])
    zeiten = iter(datetime(2026, 1, 1) + timedelta(minutes=i) for i in range(10))

    class Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(zeiten)
    monkeypatch.setattr(sicherung, "datetime", Uhr)
    sicherung.sichern(["server"])
    ablage.loeschen(a)                                 # liegt jetzt im Papierkorb, gleicher Inhalt
    shutil.rmtree(ablage.DATEN / "papierkorb")         # und endgültig weg
    for _ in range(3):
        aufnehmen(daten, f"N{_}", [f"neu {_}"])
        sicherung.sichern(["server"])
    staende = [n for n in fake.liste() if n.startswith("stand-")]
    assert len(staende) == 2
    gebraucht = set()
    s = krypto.Schluessel("geheim-genug")
    for n in staende:
        st = json.loads(s.entschluesseln((fake.wurzel / n).read_bytes()))
        gebraucht |= set(st["dateien"].values()) | {st["db"]}
    assert {n.removesuffix(".enc") for n in fake.liste("objekte")} == gebraucht


def test_faellig_wartet_ruhe_ab(daten):
    platte = daten / "platte"
    platte.mkdir()
    sicherung.einrichten({"ordner": str(platte)})
    aufnehmen(daten, "A", ["x"])
    assert sicherung.faellig(datetime.now()) == []                         # gerade erst geändert
    assert sicherung.faellig(datetime.now() + timedelta(hours=1)) == ["ordner"]
    sicherung.sichern()
    assert sicherung.faellig(datetime.now() + timedelta(hours=1)) == []


def test_kontext_warnt_ohne_sicherung(daten):
    from server import core
    assert "keine Sicherung" not in core.dokumente_text()      # leere Ablage: noch kein Grund
    aufnehmen(daten, "A", ["x"])
    assert "keine Sicherung eingerichtet" in core.dokumente_text()


def test_kennwort_nie_in_der_sicherung(daten):
    platte = daten / "platte"
    platte.mkdir()
    sicherung.einrichten({"ordner": str(platte), "kennwort": "geheim-genug"})
    aufnehmen(daten, "A", ["x"])
    sicherung.sichern()
    for f in (platte / sicherung.UNTERORDNER).rglob("*"):
        if f.is_file():
            assert b"geheim-genug" not in f.read_bytes()
    assert oct((ablage.DATEN / "geheim.json").stat().st_mode)[-3:] == "600"


def test_api(client, daten):
    platte = daten / "platte"
    platte.mkdir()
    r = client.post("/api/dokumente/sicherung", json={"ordner": str(daten / "fehlt")})
    assert r.status_code == 400 and "gibt es nicht" in r.json()["error"]
    r = client.post("/api/dokumente/sicherung", json={"ordner": str(platte)})
    assert r.json()["ziele"]["ordner"]["an"]
    aufnehmen(daten, "A", ["x"])
    r = client.post("/api/dokumente/sicherung/jetzt")
    assert r.json()["ziele"]["ordner"]["aktuell"]
    r = client.post("/api/dokumente/sicherung/pruefen", json={"ziel": "ordner"})
    assert r.json()["fehlt_anzahl"] == 0
    assert client.get("/api/dokumente/sicherung").json()["kennwort"] is False
