"""Team-Modus: Personalakten, Aufträge, Anleitungen (server/team/)."""
import json

import pytest

from server import config as cfg
from server.team import agents as ag
from server.team import anleitungen as anl
from server.team import auftraege as auf


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


WS = "/tmp/construct-test-ws"


# ---------- Belegschaft ----------
def test_erststart_rollt_die_vorlagen_aus():
    xs = ag.list_agents(WS)
    assert {a["slug"] for a in xs} == {"chef", "luna", "elara", "miranda", "janus"}
    # Die Geschäftsführung führt die Liste und heißt wie der Assistent (Fixture: Momo)
    assert xs[0]["slug"] == "chef" and xs[0]["name"] == "Momo"
    assert xs[0]["can_delegate"]
    # Jeder mitgelieferte Mitarbeiter hat einen Charakter und (außer der Chefin) ein Gesicht
    assert all(a["soul"].strip() for a in xs)
    assert all(a["avatar"].startswith("/static/team/") for a in xs if a["slug"] != "chef")


def test_mitgelieferte_gesichter_gibt_es_wirklich():
    from pathlib import Path
    static = Path(ag.__file__).resolve().parents[2] / "static"
    for a in ag.list_agents(WS):
        if a["avatar"]:
            assert (static / a["avatar"].removeprefix("/static/")).is_file(), a["avatar"]


def test_geschaeftsfuehrung_ist_der_assistent(firma):
    ag.list_agents(WS)
    chef = ag.load_agent(ag.OWNER_SLUG, WS)
    assert chef["name"] == "Momo"                         # so heißt sie auch für die Kollegen
    assert ag.anzeige(chef)["name"] == "Momo"
    assert ag.anzeige(chef)["avatar"] == "/static/cody.png"   # ohne eigenes Bild das des Assistenten
    (firma / "settings.json").write_text(json.dumps({"names": {"assistant": "Nova"}}))
    assert ag.load_agent(ag.OWNER_SLUG, WS)["name"] == "Nova"
    # In der Akte selbst steht weiter der mitgelieferte Name, nie der eigene
    assert "name: Cody" in (ag.AGENTS_DIR / "chef" / "AGENT.md").read_text()


def test_speichern_aus_der_oberflaeche_schreibt_den_assistentennamen_nicht_in_die_akte(firma):
    ag.list_agents(WS)
    neu, _ = ag.save_agent({"slug": "chef", "name": "Momo", "effort": "low"}, WS)
    assert neu["name"] == "Momo" and neu["effort"] == "low"


def test_kein_mitgelieferter_text_nennt_chanti():
    from pathlib import Path
    vorl = Path(ag.__file__).parent / "vorlagen"
    for f in vorl.rglob("*.md"):
        assert "Chanti" not in f.read_text(encoding="utf-8"), f


def test_kaputte_akte_bleibt_lesbar():
    ag.list_agents(WS)
    p = ag.AGENTS_DIR / "miranda" / "AGENT.md"
    p.write_text("---\nslug: miranda\nname: X\nmodel: gpt9\npermission_mode: bypassPermissions\ncwd: /etc\n---\n")
    a = ag.load_agent("miranda", WS)
    assert a["model"] == "sonnet"                     # Vorgabe statt Absturz
    assert a["permission_mode"] == "acceptEdits"      # bypass + ungültiges cwd wird abgelehnt
    assert any("model" in m for m in a["problems"]) and any("cwd" in m for m in a["problems"])


def test_slug_wird_nie_zum_pfad():
    a, bad = ag.validate({"slug": "../xy"}, WS)
    assert a["slug"] == "xy" and bad
    assert ag.save_agent({"slug": "../x"}, WS)[0] is None


def test_teilupdate_behaelt_unbekannte_felder():
    ag.list_agents(WS)
    vorher = ag.load_agent("luna", WS)
    neu, _ = ag.save_agent({"slug": "luna", "effort": "low"}, WS)
    assert neu["effort"] == "low" and neu["color"] == vorher["color"]
    assert neu["allowed_tools"] == vorher["allowed_tools"]


def test_entlassen_loescht_nicht():
    ag.list_agents(WS)
    assert ag.fire_agent("miranda", WS)
    assert "miranda" not in {a["slug"] for a in ag.list_agents(WS)}
    assert "miranda" in {a["slug"] for a in ag.list_agents(WS, include_fired=True)}


def test_organigramm_kappt_zyklen():
    ag.list_agents(WS)
    ag.save_agent({"slug": "chef", "reports_to": "luna"}, WS)
    baum = ag.org_tree(WS)
    assert baum["cycles"]                              # kein Absturz, kein Hängen


def test_fahigkeiten_sagen_wer_eine_shell_hat():
    ag.list_agents(WS)
    assert "Shell" in ag.faehigkeiten(ag.load_agent("luna", WS))
    assert "Shell" not in ag.faehigkeiten(ag.load_agent("chef", WS))


def test_rechte_nach_aufgabe():
    # Kevin, 06.10.2026: jeder bekommt, was er für seine Aufgabe braucht. Shell und
    # Web zugleich ist erlaubt; die Geschäftsführung schreibt weiterhin keinen Code.
    xs = {a["slug"]: a for a in ag.list_agents(WS)}
    assert not any(a["problems"] for a in xs.values())
    for slug in ("luna", "elara", "miranda", "janus"):
        assert {"Bash", "WebSearch", "WebFetch"} <= set(xs[slug]["allowed_tools"]), slug
    chef = set(xs["chef"]["allowed_tools"])
    assert "WebSearch" in chef and not {"Bash", "Write", "Edit"} & chef
    assert xs["chef"]["permission_mode"] == "auto"
    # Janus schreibt seinen Prüfbericht, ändert aber nichts (kein Edit)
    assert "Write" in xs["janus"]["allowed_tools"] and "Edit" not in xs["janus"]["allowed_tools"]


def test_shell_und_web_zusammen_ist_kein_mangel():
    a, bad = ag.validate({"slug": "neu", "allowed_tools": "Read, Bash, WebFetch"}, WS)
    assert a["allowed_tools"] == ["Read", "Bash", "WebFetch"] and not bad


def test_unveraenderte_alte_werkzeugliste_wird_nachgezogen(firma):
    ag.list_agents(WS)
    neu_liste = "allowed_tools: " + ag._werkzeuge_der_vorlage("luna")
    for alt in ag.ALTE_WERKZEUGE["luna"]:
        f = firma / "firma" / "agents" / "luna" / "AGENT.md"
        # Eigener Text: die Akte ist angepasst, nur die Werkzeugzeile folgt der Vorlage
        f.write_text(f.read_text().replace(neu_liste, "allowed_tools: " + alt)
                     + "\nEigener Text bleibt.\n")
        a = ag.load_agent("luna", WS)
        assert "WebSearch" in a["allowed_tools"] and not a["problems"]
        assert neu_liste in f.read_text() and "Eigener Text bleibt." in f.read_text()
    # Eigene Liste: bleibt
    j = firma / "firma" / "agents" / "janus" / "AGENT.md"
    j.write_text(j.read_text().replace("allowed_tools: " + ag._werkzeuge_der_vorlage("janus"),
                                       "allowed_tools: Read, Bash, WebFetch"))
    assert ag.load_agent("janus", WS)["allowed_tools"] == ["Read", "Bash", "WebFetch"]


def _vorlage(lang, slug, name):
    d = "agents.default.en" if lang == "en" else "agents.default"
    return (ag.VORLAGEN_DIR / d / slug / name).read_text(encoding="utf-8")


def test_sprachwechsel_zieht_unveraenderte_akten_nach(firma):
    ag.list_agents(WS)
    akte = firma / "firma" / "agents"
    eigen = akte / "elara" / "SOUL.md"
    eigen.write_text("Elara, von Hand angepasst.\n")
    (firma / "settings.json").write_text(json.dumps({"lang": "en"}))
    xs = {a["slug"]: a for a in ag.list_agents(WS)}
    assert (akte / "luna" / "SOUL.md").read_text() == _vorlage("en", "luna", "SOUL.md")
    assert (akte / "chef" / "AGENT.md").read_text() == _vorlage("en", "chef", "AGENT.md")
    assert xs["luna"]["title"] == "Backend and engineering"
    assert eigen.read_text() == "Elara, von Hand angepasst.\n"          # angepasst: bleibt
    assert (akte / "elara" / "AGENT.md").read_text() == _vorlage("en", "elara", "AGENT.md")
    # und zurück
    (firma / "settings.json").write_text(json.dumps({"lang": "de"}))
    ag.list_agents(WS)
    assert (akte / "luna" / "SOUL.md").read_text() == _vorlage("de", "luna", "SOUL.md")


def test_akte_einer_frueheren_fassung_folgt_der_vorlage(firma):
    # So steht es in Installationen, die vor der Buchführung ausgerollt wurden:
    # keine .vorlagen.json, die Akte entspricht einer älteren mitgelieferten Fassung.
    import hashlib
    ag.list_agents(WS)
    akte = firma / "firma" / "agents" / "janus" / "AGENT.md"
    alt = _vorlage("de", "janus", "AGENT.md").replace(
        "allowed_tools: " + ag._werkzeuge_der_vorlage("janus"),
        "allowed_tools: Read, Bash, Grep, Glob").replace("prueft: ja\n", "")
    assert hashlib.sha256(alt.encode()).hexdigest() in ag._fruehere()["janus/AGENT.md"]
    akte.write_text(alt)
    (ag.AGENTS_DIR / ".vorlagen.json").unlink()
    ag._ABGEGLICHEN.clear()
    ag.load_agent("janus", WS)
    assert akte.read_text() == _vorlage("de", "janus", "AGENT.md")


def test_englische_vorlagen_sind_vollstaendig():
    # Die englischen Charaktere fielen unter die .gitignore-Regel der Persona
    # (SOUL.md) und fehlten in jedem Klon.
    for d in (ag.VORLAGEN_DIR / "agents.default").iterdir():
        for name in ag.AKTEN_DATEIEN:
            assert (ag.VORLAGEN_DIR / "agents.default.en" / d.name / name).exists(), (d.name, name)


def test_historie_nur_fuer_vorhandene_akten():
    ag.list_agents(WS)
    ag.historie_eintragen("luna", "Login-Fix", "mitgearbeitet", ["/x/a.py"])
    ag.historie_eintragen("gibtsnicht", "egal", "geleitet")
    assert "Login-Fix" in ag.historie_text("luna")
    assert not (ag.AGENTS_DIR / "gibtsnicht").exists()


def test_user_merken_landet_in_den_ergaenzungen_nicht_in_user_md(firma):
    ag.user_read()
    ok, _ = ag.user_append("mag Kaffee", "luna")
    assert ok and "mag Kaffee" in ag.user_read()                 # die Firma liest es
    assert "mag Kaffee" not in (firma / "USER.md").read_text()   # der Chat-Assistent nicht
    assert "mag Kaffee" in ag.ergaenzungen_read()


def test_user_md_nur_anhaengen():
    ok, _ = ag.user_append("mag Kaffee", "luna")
    assert ok and "mag Kaffee" in ag.user_read()
    assert ag.user_append("mag Kaffee", "miranda") == (False, "steht schon drin")
    assert ag.user_append("   ", "miranda")[0] is False


def test_anrede_setzt_den_namen_des_nutzers_ein():
    assert ag.anrede("Kevins Worte an Kevin.") == "Annas Worte an Anna."
    assert ag.anrede("von kevin") == "von kevin"       # das Kürzel im Verlauf bleibt


def test_anrede_laesst_eingesetzte_inhalte_stehen():
    from server.team import prompts
    t = auf.neu("Film", "Schreib über Kevin Costner.")
    a = ag.load_agent("luna", WS)
    p = prompts.auftrags_prompt(a, t, {"von": "kevin", "art": "auftrag",
                                       "text": "Kevin Costner, bitte."})
    assert "Annas Worte: Schreib über Kevin Costner." in p
    assert "Kevin Costner, bitte." in p and "Anna Costner" not in p


def test_vorlage_der_installation_sticht(firma):
    assert "Hausstil" in ag.style_read()
    (ag.FIRMA_DIR).mkdir(parents=True, exist_ok=True)
    (ag.FIRMA_DIR / "HAUSSTIL.md").write_text("# Mein Stil\n")
    assert ag.style_read().startswith("# Mein Stil")


# ---------- Anleitungen ----------
def test_anleitung_anlegen_lesen_verbessern():
    ok, _ = anl.anlegen("playwright-bestaetigen", "Wenn ein Klick eine Seite neu lädt",
                        "1. expect_navigation benutzen\n2. danach warten, sonst geht der POST verloren", "miranda")
    assert ok
    assert anl.lesen("playwright-bestaetigen")["von"] == "miranda"
    anl.benutzt_vermerken("playwright-bestaetigen")
    anl.benutzt_vermerken("playwright-bestaetigen")
    ok, msg = anl.anlegen("playwright-bestaetigen", "Wenn ein Klick eine Seite neu lädt",
                          "1. expect_navigation benutzen\n2. danach warten und das Ergebnis lesen", "luna")
    assert ok and "aktualisiert" in msg
    x = anl.lesen("playwright-bestaetigen")
    assert x["von"] == "miranda" and x["benutzt"].startswith("2")   # Zähler und Urheber bleiben
    assert "playwright-bestaetigen" in anl.index()


def test_anleitung_name_darf_kein_pfad_sein():
    ok, _ = anl.anlegen("../../etc/x", "Wenn irgendwas ist", "x" * 80, "miranda")
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


def test_chef_prompt_ist_der_assistent_plus_firmenzusatz(firma, monkeypatch):
    soul = firma / "SOUL.md"
    soul.write_text("Ich bin Momo, dein Assistent.", encoding="utf-8")
    monkeypatch.setitem(cfg.PERSONA_FILES, "soul", (soul, None))
    ag.list_agents(WS)
    from server.team import prompts as pr
    p = pr.agent_system_prompt(ag.load_agent("chef", WS), WS)
    assert p.startswith("Ich bin Momo") and "# Zusätzlich: du führst die Firma" in p
    # Die Mitarbeiter bekommen ihren eigenen Charakter, nicht den des Assistenten
    q = pr.agent_system_prompt(ag.load_agent("luna", WS), WS)
    assert "Ich bin Momo" not in q and "Backend und Technik" in q


# ---------- Kleinzeug aus dem Großtest ----------
@pytest.mark.parametrize("inhalt", ["[]", "{}", '{"status": 5, "verbraucht": "x", "titel": null}',
                                    '{"status": "erfunden"}', "kaputt"])
def test_verkorkste_auftragsdatei_legt_nichts_lahm(firma, inhalt):
    t = auf.neu("Heil", "brief")
    d = firma / "firma" / "auftraege" / "0badc0de"
    d.mkdir(parents=True)
    (d / "ticket.json").write_text(inhalt)
    xs = auf.alle()
    assert t["id"] in [x["id"] for x in xs]
    for x in xs:
        assert x["status"] in auf.STATUS and isinstance(x["verbraucht"]["hops"], int)
        assert isinstance(x["titel"], str)


@pytest.mark.parametrize("tid", ["..", "../../settings", "ABCDEF12", "abc", ""])
def test_auftrags_id_wird_nie_zum_pfad(tid):
    assert auf.laden(tid) is None and auf.verlauf(tid) == []


@pytest.mark.parametrize("ausdruck", ["-" * 1990 + "1", "(" * 999 + "1" + ")" * 999, "1+" * 1500 + "1"])
def test_rechnen_mit_absurden_ausdruecken_ist_ein_rechenfehler(ausdruck):
    from server.team import rechner
    with pytest.raises(rechner.CalcError):
        rechner.calculate(ausdruck)


def test_prüfstand_schalter_landet_nicht_in_settings(firma, monkeypatch):
    monkeypatch.setenv("CONSTRUCT_TEAM", "1")
    assert cfg.load_settings()["team"]["aktiv"]
    assert cfg.apply_patch({"theme": "matrix"})["team"]["aktiv"]
    assert not json.loads((firma / "settings.json").read_text())["team"]["aktiv"]


def test_fingerabdruck_nur_von_echten_dateien(tmp_path):
    from server.team import engine
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert len(engine._sha(str(f))) == 12
    assert engine._sha("/dev/zero") == "" and engine._sha(str(tmp_path)) == ""


def test_geschaeftsfuehrung_laesst_sich_nicht_entlassen(firma):
    ag.list_agents(WS)
    vorher = (firma / "firma" / "agents" / "chef" / "AGENT.md").read_text()
    assert not ag.fire_agent("chef", WS)
    assert (firma / "firma" / "agents" / "chef" / "AGENT.md").read_text() == vorher


# ---------- Englische Installation (F2) ----------
@pytest.fixture()
def englisch(firma):
    (firma / "settings.json").write_text(json.dumps(
        {"lang": "en", "names": {"user": "Anna", "assistant": "Momo"}}))
    return firma


def test_englische_installation_bekommt_englische_belegschaft(englisch):
    xs = {a["slug"]: a for a in ag.list_agents(WS)}
    assert xs["luna"]["title"] == "Backend and engineering"
    assert all(not a["problems"] for a in xs.values())
    assert "You" in xs["luna"]["soul"] and "Du " not in xs["luna"]["soul"]
    # dieselben Werkzeuge wie die deutsche Vorlage
    de = ag._split_frontmatter((ag.DEFAULTS_DIR / "luna" / "AGENT.md").read_text())[0]
    assert xs["luna"]["allowed_tools"] == ag._as_list(ag._fm_get(de, "allowed_tools"))


def test_englischer_systemprompt_und_zug(englisch):
    from server.team import prompts
    a = ag.load_agent("luna", WS)
    sp = prompts.agent_system_prompt(a, WS)
    assert "House style" in sp and "You work in a company of AI employees" in sp
    assert "Anna" in sp and "Kevin" not in sp
    for deutsch in ("Hausstil", "Belegschaft:", "Beende deinen Zug", "Woran du"):
        assert deutsch not in sp, deutsch
    t = auf.neu("Film", "Write about Kevin Costner.")
    p = prompts.auftrags_prompt(a, t, {"von": "kevin", "art": "auftrag", "text": "Go."})
    assert "# Job: Film" in p and "Anna's words: Write about Kevin Costner." in p
    assert "End your turn" in p


def test_englische_bremsen_und_meldungen(englisch):
    from server.team import guards
    t = auf.neu("x", "y")
    verlauf = [{"von": "luna", "an": "elara", "art": "frage", "text": str(i), "ts": 1}
               for i in range(10)]
    bremse, grund = guards.pruefe(t, {"von": "luna", "an": "elara"}, verlauf)
    assert bremse == "hin_und_her" and "going in circles" in grund
    assert guards.name("stille") == "turn hangs"
    assert ag.user_append("", "luna") == (False, "empty entry")


def test_deutsch_bleibt_vorgabe(firma):
    xs = {a["slug"]: a for a in ag.list_agents(WS)}
    assert xs["luna"]["title"] == "Backend und Technik"
    assert "Hausstil" in ag.style_read()


def test_rechner_und_anrede_sprechen_englisch(firma):
    from server.team import rechner
    (firma / "settings.json").write_text(json.dumps({"lang": "en"}))
    with pytest.raises(rechner.CalcError, match="Division by zero"):
        rechner.calculate("1/0")
    assert ag.anrede("Kevin's job") == "The user's job"
    assert ag.anrede("Ask Kevin. Kevin decides, as Kevins wish.") == \
        "Ask the user. The user decides, as the user's wish."
    assert ag.anrede("- **Kevin** wants results") == "- **The user** wants results"


def test_belegschaft_zeigt_wer_prueft(firma):
    xs = {a["slug"]: a for a in ag.list_agents(WS)}
    assert [s for s, a in sorted(xs.items()) if a["prueft"]] == ["janus", "miranda"]
    j = ag.faehigkeiten(xs["janus"])
    assert j.startswith("Prüfer (baut nicht selbst)") and "schreibt nur Berichte" in j
    assert "Prüfer" not in ag.faehigkeiten(xs["luna"])
    # Angepasste Akte von vor dem Feld: bleibt Prüfer
    f = firma / "firma" / "agents" / "miranda" / "AGENT.md"
    f.write_text(f.read_text().replace("prueft: ja\n", "").replace("model: sonnet", "model: opus"))
    assert ag.load_agent("miranda", WS)["prueft"] is True
    (firma / "settings.json").write_text(json.dumps({"lang": "en"}))
    assert ag.faehigkeiten(ag.load_agent("janus", WS)).startswith("reviewer (does not build)")


def test_angepasste_akte_bekommt_titel_in_der_neuen_sprache(firma):
    ag.list_agents(WS)
    f = firma / "firma" / "agents" / "miranda" / "AGENT.md"
    f.write_text(f.read_text().replace("model: sonnet", "model: opus"))   # in ⚙ umgestellt
    (firma / "settings.json").write_text(json.dumps({"lang": "en"}))
    a = ag.load_agent("miranda", WS)
    assert a["title"] == "Quality assurance" and a["model"] == "opus"
    assert a["model_grund"] == ag._feld_der_vorlage("miranda", "model_grund",
                                                   ag.VORLAGEN_DIR / "agents.default.en")
    # Eigener Titel bleibt
    f.write_text(f.read_text().replace("title: Quality assurance", "title: Testchefin"))
    (firma / "settings.json").write_text(json.dumps({"lang": "de"}))
    assert ag.load_agent("miranda", WS)["title"] == "Testchefin"
