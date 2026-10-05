"""Team-Modus: Personalakten, Aufträge, Anleitungen (server/team/)."""
import json

import pytest

from server import config as cfg
from server.team import agents as ag
from server.team import anleitungen as anl
from server.team import auftraege as auf
from server.team import hiring


@pytest.fixture(autouse=True)
def firma(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "FIRMA_DIR", tmp_path / "firma")
    monkeypatch.setattr(ag, "AGENTS_DIR", tmp_path / "firma" / "agents")
    monkeypatch.setattr(ag, "USER_FILE", tmp_path / "USER.md")
    monkeypatch.setattr(ag, "ERGAENZUNGEN_FILE", tmp_path / "firma" / "USER-ergaenzungen.md")
    monkeypatch.setattr(anl, "DIR", tmp_path / "firma" / "anleitungen")
    monkeypatch.setattr(auf, "AUFTRAEGE_DIR", tmp_path / "firma" / "auftraege")
    (tmp_path / "settings.json").write_text(json.dumps(
        {"lang": "de", "names": {"user": "Anna", "assistant": "Momo"}}))
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")
    auf._UEBERSICHT.clear()
    return tmp_path


WS = "/home/z0mb1"


# ---------- Belegschaft ----------
def test_erststart_rollt_die_vorlagen_aus():
    xs = ag.list_agents(WS)
    assert {a["slug"] for a in xs} == {"chef", "entwickler", "pruefer"}
    # Die Geschäftsführung führt die Liste und heißt wie der Assistent
    assert xs[0]["slug"] == "chef" and xs[0]["name"] == "Momo"
    assert xs[0]["can_delegate"] and xs[0]["can_hire"]


def test_geschaeftsfuehrung_ist_der_assistent_auch_nach_umbenennen(firma):
    ag.list_agents(WS)
    (firma / "settings.json").write_text(json.dumps({"names": {"assistant": "Chanti"}}))
    assert ag.load_agent(ag.OWNER_SLUG, WS)["name"] == "Chanti"


def test_kaputte_akte_bleibt_lesbar():
    ag.list_agents(WS)
    p = ag.AGENTS_DIR / "pruefer" / "AGENT.md"
    p.write_text("---\nslug: pruefer\nname: X\nmodel: gpt9\npermission_mode: bypassPermissions\ncwd: /etc\n---\n")
    a = ag.load_agent("pruefer", WS)
    assert a["model"] == "sonnet"                     # Vorgabe statt Absturz
    assert a["permission_mode"] == "acceptEdits"      # bypass + ungültiges cwd wird abgelehnt
    assert any("model" in m for m in a["problems"]) and any("cwd" in m for m in a["problems"])


def test_slug_wird_nie_zum_pfad():
    a, bad = ag.validate({"slug": "../xy"}, WS)
    assert a["slug"] == "xy" and bad
    assert ag.save_agent({"slug": "../x"}, WS)[0] is None


def test_teilupdate_behaelt_unbekannte_felder():
    ag.list_agents(WS)
    vorher = ag.load_agent("entwickler", WS)
    neu, _ = ag.save_agent({"slug": "entwickler", "effort": "low"}, WS)
    assert neu["effort"] == "low" and neu["color"] == vorher["color"]
    assert neu["allowed_tools"] == vorher["allowed_tools"]


def test_entlassen_loescht_nicht():
    ag.list_agents(WS)
    assert ag.fire_agent("pruefer", WS)
    assert "pruefer" not in {a["slug"] for a in ag.list_agents(WS)}
    assert "pruefer" in {a["slug"] for a in ag.list_agents(WS, include_fired=True)}


def test_organigramm_kappt_zyklen():
    ag.list_agents(WS)
    ag.save_agent({"slug": "chef", "reports_to": "entwickler"}, WS)
    baum = ag.org_tree(WS)
    assert baum["cycles"]                              # kein Absturz, kein Hängen


def test_fahigkeiten_sagen_wer_eine_shell_hat():
    ag.list_agents(WS)
    assert "Shell" in ag.faehigkeiten(ag.load_agent("entwickler", WS))
    assert "Shell" not in ag.faehigkeiten(ag.load_agent("chef", WS))


def test_historie_nur_fuer_vorhandene_akten():
    ag.list_agents(WS)
    ag.historie_eintragen("entwickler", "Login-Fix", "mitgearbeitet", ["/x/a.py"])
    ag.historie_eintragen("gibtsnicht", "egal", "geleitet")
    assert "Login-Fix" in ag.historie_text("entwickler")
    assert not (ag.AGENTS_DIR / "gibtsnicht").exists()


def test_user_merken_landet_in_den_ergaenzungen_nicht_in_user_md(firma):
    ag.user_read()
    ok, _ = ag.user_append("mag Kaffee", "entwickler")
    assert ok and "mag Kaffee" in ag.user_read()                 # die Firma liest es
    assert "mag Kaffee" not in (firma / "USER.md").read_text()   # der Chat-Assistent nicht
    assert "mag Kaffee" in ag.ergaenzungen_read()


def test_user_md_nur_anhaengen():
    ok, _ = ag.user_append("mag Kaffee", "entwickler")
    assert ok and "mag Kaffee" in ag.user_read()
    assert ag.user_append("mag Kaffee", "pruefer") == (False, "steht schon drin")
    assert ag.user_append("   ", "pruefer")[0] is False


def test_anrede_setzt_den_namen_des_nutzers_ein():
    assert ag.anrede("Kevins Worte an Kevin.") == "Annas Worte an Anna."
    assert ag.anrede("von kevin") == "von kevin"       # das Kürzel im Verlauf bleibt


def test_vorlage_der_installation_sticht(firma):
    assert "Hausstil" in ag.style_read()
    (ag.FIRMA_DIR).mkdir(parents=True, exist_ok=True)
    (ag.FIRMA_DIR / "HAUSSTIL.md").write_text("# Mein Stil\n")
    assert ag.style_read().startswith("# Mein Stil")


# ---------- Anleitungen ----------
def test_anleitung_anlegen_lesen_verbessern():
    ok, _ = anl.anlegen("playwright-bestaetigen", "Wenn ein Klick eine Seite neu lädt",
                        "1. expect_navigation benutzen\n2. danach warten, sonst geht der POST verloren", "pruefer")
    assert ok
    assert anl.lesen("playwright-bestaetigen")["von"] == "pruefer"
    anl.benutzt_vermerken("playwright-bestaetigen")
    anl.benutzt_vermerken("playwright-bestaetigen")
    ok, msg = anl.anlegen("playwright-bestaetigen", "Wenn ein Klick eine Seite neu lädt",
                          "1. expect_navigation benutzen\n2. danach warten und das Ergebnis lesen", "entwickler")
    assert ok and "aktualisiert" in msg
    x = anl.lesen("playwright-bestaetigen")
    assert x["von"] == "pruefer" and x["benutzt"].startswith("2")   # Zähler und Urheber bleiben
    assert "playwright-bestaetigen" in anl.index()


def test_anleitung_name_darf_kein_pfad_sein():
    ok, _ = anl.anlegen("../../etc/x", "Wenn irgendwas ist", "x" * 80, "pruefer")
    assert not ok
    assert anl.lesen("../x") is None


def test_anleitung_ohne_wann_oder_zu_duenn():
    assert not anl.anlegen("ok-name", "kurz", "x" * 80, "p")[0]
    assert not anl.anlegen("ok-name", "ausführlich genug erklärt", "zu dünn", "p")[0]


# ---------- Aufträge ----------
def test_auftrag_verlauf_ist_nur_anhaengend_und_toleriert_abgeschnittenes():
    t = auf.neu("Titel", "Brief", owner="chef")
    auf.anhaengen(t["id"], {"von": "kevin", "an": "chef", "art": "auftrag", "text": "los"})
    with (auf._dir(t["id"]) / "thread.jsonl").open("a") as f:
        f.write('{"von": "chef", "an"')                   # Absturz mitten in der Zeile
    assert [e["text"] for e in auf.verlauf(t["id"])] == ["los"]


def test_quittierung_und_offene_nachrichten():
    t = auf.neu("T", "B")
    m = auf.anhaengen(t["id"], {"von": "kevin", "an": "chef", "art": "auftrag", "text": "x"})
    assert [n["id"] for n in auf.offene_nachrichten(t["id"])] == [m["id"]]
    auf.quittieren(t["id"], m["id"])
    assert auf.offene_nachrichten(t["id"]) == []


def test_uebersicht_zaehlt_ohne_quittungen():
    t = auf.neu("T", "B")
    auf.anhaengen(t["id"], {"von": "kevin", "an": "chef", "art": "auftrag", "text": "x"})
    m = auf.anhaengen(t["id"], {"von": "chef", "an": "kevin", "art": "ergebnis", "text": "y"})
    auf.quittieren(t["id"], m["id"])
    u = auf.uebersicht(t["id"])
    assert u["msgs"] == 2 and u["letzte_von"] == "chef"


def test_titel_wird_gekuerzt_und_leerer_brief_hat_einen_titel():
    assert len(auf.neu("x" * 500, "b")["titel"]) == 120
    assert auf.neu("", "")["titel"] == "Auftrag"


# ---------- Einstellungsverfahren ----------
def test_kandidat_wird_zur_akte():
    k = {"slug": " QA ", "name": "Tessa", "titel": "Prüferin", "systemprompt": "Du prüfst.",
         "model": "sonnet", "effort": "high", "allowed_tools": ["Read"], "can_delegate": False}
    akte = hiring.als_akte(k, WS)
    assert akte["slug"] == "qa" and akte["reports_to"] == ag.OWNER_SLUG
    neu, bad = ag.save_agent(akte, WS)
    assert neu["slug"] == "qa" and not bad and neu["soul"] == "Du prüfst."


def test_prompt_der_kandidatensuche_spricht_den_nutzer_mit_namen_an():
    ag.list_agents(WS)
    p = hiring._prompt("Texterin", "weil", "", ag.list_agents(WS), "")
    assert "Anna" in p and "Kevin" not in p
    assert p.startswith("[firma-intern]")
