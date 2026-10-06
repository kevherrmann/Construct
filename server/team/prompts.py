"""Was ein Mitarbeiter liest: Systemprompt und die Nachricht des Zuges.

Zwei Dinge, die sich nie vermischen dürfen:

  * der SYSTEMPROMPT (agent_system_prompt) ist über einen ganzen Auftrag hinweg
    stabil — nur so kann Claude Code ihn zwischenspeichern;
  * die NACHRICHT des Zuges (auftrags_prompt) trägt alles Veränderliche:
    Auftragslage, Postfach, womit der Zug enden muss.

Was an ein Modell geht, läuft durch ag.anrede(): die mitgelieferten Regeln
sprechen den Nutzer mit Kevins Namen an, hier wird daraus der Name der
Installation.
"""
from server import config as cfg
from server.team import agents as ag
from server.team import anleitungen as anl
from server.team import auftraege as auf
from server.team import guards


def auftrags_prompt(a: dict, t: dict, nachricht: dict) -> str:
    """Die NACHRICHT des Zuges — alles Veraenderliche gehoert hierher.

    Auftragslage und die eigentliche Nachricht aendern sich bei jedem Zug.
    Stuende das im Systemprompt, waere dessen Zwischenspeicher jedes Mal
    wertlos — gemessen hat genau diese Trennung den zweiten Zug achtmal
    billiger gemacht.

    Der Zaehlerstand der Bremsen steht hier BEWUSST nicht drin: wer bei jedem
    Zug liest, wie viel er noch darf, plant danach statt zu arbeiten. Erst wenn
    es wirklich eng wird, kommt ein Satz dazu.
    """
    kopf = [
        cfg.L(f"# Auftrag: {t['titel']}", f"# Job: {t['titel']}"),
        cfg.L(f"Kevins Worte: {t['brief']}", f"Kevin's words: {t['brief']}"),
    ]
    rest = guards.rest_schritte(t, auf.verlauf(t["id"]))
    if rest <= guards.WARNUNG_AB:
        kopf.append(cfg.L(f"Achtung: noch {rest} Schritte, dann hält der Auftrag an und Kevin muss "
                          f"ran. Liefere lieber ein ehrliches Teilergebnis mit dem, was fehlt.",
                          f"Careful: {rest} steps left, then the job stops and Kevin has to step "
                          f"in. Better deliver an honest partial result that says what is missing."))
    if t.get("artefakte"):
        kopf.append(cfg.L("Bisher angefasste Dateien: ", "Files touched so far: ")
                    + ", ".join(x["pfad"] for x in t["artefakte"][-8:]))
    offen = ausstehend(a["slug"], auf.verlauf(t["id"]))
    if offen and nachricht.get("art") != "auftrag":
        kopf.append(cfg.L("Von dir beauftragt und noch ohne Ergebnis: ",
                          "Briefed by you and still without a result: ") + ", ".join(offen))
    # Was schon im Postfach liegt, aber erst im naechsten Zug kommt. Ohne den
    # Satz sagte Luna am 11.09.2026 "ich warte auf Miranda", waehrend Mirandas
    # Ergebnis laengst da war — nur hinter Raukes in der Reihe.
    liegt = [n for n in auf.offene_nachrichten(t["id"])
             if n.get("an") == a["slug"] and n.get("id") != nachricht.get("id")]
    if liegt:
        kopf.append(cfg.L("Liegt schon für dich bereit und kommt im nächsten Zug von selbst "
                          "(nicht darauf warten, nicht danach fragen): ",
                          "Already waiting for you and arrives by itself in your next turn "
                          "(do not wait for it, do not ask for it): ")
                    + ", ".join(f"{n.get('art')} {cfg.L('von', 'from')} {n.get('von')}" for n in liegt))
    absender = nachricht.get("von") or "kevin"
    wer = "Kevin" if absender == "kevin" else absender
    art = cfg.L({"auftrag": "beauftragt dich", "frage": "fragt dich",
                 "antwort": "antwortet dir", "ergebnis": "liefert dir"},
                {"auftrag": "briefs you", "frage": "asks you",
                 "antwort": "answers you", "ergebnis": "delivers to you"}
                ).get(nachricht.get("art"), cfg.L("schreibt dir", "writes to you"))
    kopf.append(f"\n## {wer} {art}:\n\n{nachricht.get('text', '')}")
    kopf.append("\n" + zug_abschluss(a, t, nachricht))
    return ag.anrede("\n".join(kopf), roh=(t["titel"], t["brief"], nachricht.get("text", "")))


def zug_abschluss(a: dict, t: dict, nachricht: dict) -> str:
    """Der letzte Satz vor dem Handeln: womit dieser Zug enden muss.

    Warum das hier steht, obwohl PROTOCOL.md es laengst sagt: dort ist es Punkt
    fuenf einer Liste, und danach kommen noch zwei Dokumente. Gelesen wird es,
    befolgt nicht. Der Pruefstand hat am 03.09.2026 an zwei von vier Faellen
    gezeigt, wie das ausgeht — eine Mitarbeiterin fasst ein fertiges Ergebnis
    korrekt zusammen und ruft `liefern` nicht auf, eine andere stellt eine gute
    Rueckfrage und ruft `eskalieren` nicht auf. Inhaltlich beide richtig, nur nie
    am Bus angekommen; die Notbremse `stiller_zug` holt dann den Nutzer zu einem Auftrag,
    der eigentlich fertig war.

    Deshalb steht die Regel zusaetzlich als LETZTE Zeile der Nachricht, direkt
    vor dem Handeln. Und sie zaehlt nicht alle Werkzeuge auf, sondern die ein
    bis zwei, die in dieser Lage richtig sind — eine Liste mit allen ist wieder
    nur Protokoll zum Ueberlesen.
    """
    schluss = cfg.L("Ein Zug ohne Bus-Aufruf hält den ganzen Auftrag an.",
                    "A turn without a bus call stops the whole job.")
    art = nachricht.get("art")

    if art == "frage":
        return cfg.L(f"**Beende deinen Zug mit `antworten`.** {schluss}",
                     f"**End your turn with `antworten` (answer).** {schluss}")

    if art == "ergebnis" and a["slug"] == t["owner"]:
        # Der heikelste Fall: der Auftrag ist faktisch fertig, und genau hier
        # blieb er im Pruefstand liegen.
        offen = ausstehend(a["slug"], auf.verlauf(t["id"]))
        if offen:
            return cfg.L("**Du führst diesen Auftrag.** Es arbeiten noch: "
                         + ", ".join(offen) + ". Warte deren Ergebnis ab, bevor du "
                         "lieferst — `notiz`, wenn du dir etwas festhalten willst, "
                         f"sonst vergib den nächsten Schritt. {schluss}",
                         "**You lead this job.** Still working: "
                         + ", ".join(offen) + ". Wait for their result before you "
                         "deliver — `notiz` (note) if you want to record something, "
                         f"otherwise hand out the next step. {schluss}")
        return cfg.L("**Du führst diesen Auftrag.** Prüfe, ob er damit erledigt "
                     "ist — wenn ja, `liefern` (das geht an Kevin und schließt den "
                     f"Auftrag ab). Wenn nicht, vergib den nächsten Schritt. {schluss}",
                     "**You lead this job.** Check whether this completes it — if so, "
                     "`liefern` (deliver; it goes to Kevin and closes the job). If not, "
                     f"hand out the next step. {schluss}")

    if art == "auftrag" and nachricht.get("groesse") == "klein":
        # Der Umsetzer schreibt hier fuer Kevin, nicht fuer die
        # Geschaeftsfuehrung — die liest sein Ergebnis nicht mehr.
        return cfg.L("**Das ist ein Kleinauftrag: dein `liefern` geht direkt an Kevin "
                     "und schließt den Auftrag ab.** Schreib das Ergebnis also für ihn — "
                     "was jetzt anders ist, was er wissen muss. Kommst du ohne ihn nicht "
                     f"weiter: `eskalieren`. {schluss}",
                     "**This is a small job: your `liefern` (deliver) goes straight to "
                     "Kevin and closes the job.** So write the result for Kevin — what is "
                     "different now, what Kevin needs to know. If you cannot go on without "
                     f"Kevin: `eskalieren` (escalate). {schluss}")

    if art in ("auftrag", "antwort") and a.get("can_delegate"):
        # Wer verteilen darf, soll das auch tun. Stand hier frueher nur
        # "liefern oder eskalieren", war das eine Einladung an die
        # Geschaeftsfuehrung, es doch schnell selbst zu machen.
        return cfg.L("**Beende deinen Zug mit `beauftragen`** (du gibst die Arbeit "
                     "an den Richtigen weiter — unabhängige Teile auch an mehrere), "
                     "**`liefern`** (nichts zu verteilen, dein Teil steht) **oder "
                     f"`eskalieren`** (du kommst ohne Kevin nicht weiter). {schluss}",
                     "**End your turn with `beauftragen`** (brief: you pass the work to "
                     "the right person — independent parts also to several), "
                     "**`liefern`** (deliver: nothing to hand out, your part is done) **or "
                     f"`eskalieren`** (escalate: you cannot go on without Kevin). {schluss}")

    return cfg.L("**Beende deinen Zug mit `liefern`** (dein Teil steht) **oder "
                 f"`eskalieren`** (du kommst ohne Kevin nicht weiter). {schluss}",
                 "**End your turn with `liefern`** (deliver: your part is done) **or "
                 f"`eskalieren`** (escalate: you cannot go on without Kevin). {schluss}")


def ausstehend(slug: str, verlauf: list) -> list:
    """Wen dieser Mitarbeiter beauftragt hat, ohne bisher ein Ergebnis zu haben.

    Gebraucht, seit ein Verteiler mehrere Leute in EINEM Zug beauftragen darf:
    kommt das erste Ergebnis herein, muss er wissen, dass noch eines fehlt —
    sonst liefert er an Kevin, waehrend Elara noch an der Oberflaeche sitzt.
    """
    offen = []
    for e in verlauf:
        if e.get("art") == "auftrag" and e.get("von") == slug and e.get("an"):
            if e["an"] not in offen:
                offen.append(e["an"])
        elif e.get("art") == "ergebnis" and e.get("an") == slug and e.get("von") in offen:
            offen.remove(e["von"])
    return offen


def agent_system_prompt(a: dict, workspace) -> str:
    """SOUL + eigenes Gedächtnis + das gemeinsame Wissen über den Nutzer.

    Reihenfolge und Inhalt sind bewusst STABIL: alles hier ändert sich über ein
    Gespräch hinweg nicht, deshalb kann Claude Code den Block zwischenspeichern.
    Alles Veränderliche (Datum, Auftragslage) gehört in die Nachricht, nicht
    hierher — sonst ist der Zwischenspeicher bei jedem Zug wertlos.

    Am 04.09.2026 einmal umsortiert und wieder zurückgebaut — damit es niemand
    ein zweites Mal versucht: Die Idee war, die 16 617 Zeichen, die bei ALLEN
    Mitarbeitern gleich sind (HAUSSTIL, PROTOCOL, GESTALTUNG, USER.md), nach
    vorn zu ziehen. Weil die SOUL pro Person verschieden ist und vorn steht,
    beginnt jeder Systemprompt anders, und der gemeinsame Teil landet fünfmal
    einzeln im Zwischenspeicher statt einmal geteilt.

    Am Modell stimmt das auch — nur greift es hier nicht. Der Prompt geht per
    `--append-system-prompt-file` an Claude Code, und WO die Speichermarken
    gesetzt werden, entscheidet Claude Code, nicht wir; die API sieht unseren
    Block am Stück. Gemessen mit dem Prüfstand, je ein Lauf über sieben Fälle
    mit kaltem Speicher:

        SOUL zuerst:      1 393 032 gelesen / 160 844 geschrieben  (90 %)
        gemeinsam zuerst: 1 493 958 gelesen / 182 145 geschrieben  (89 %)

    Also kein Gewinn. Die Quote liegt ohnehin bei rund 90 % — hier ist nichts
    zu holen, solange Claude Code dazwischen steht.
    """
    soul = (a.get("soul") or cfg.L(f"Du bist {a['name']}, {a['title']}.",
                                   f"You are {a['name']}, {a['title']}.")).replace("{name}", a["name"])
    if a["slug"] == ag.OWNER_SLUG:
        # Die Geschäftsführung ist der Assistent: zuerst sein Charakter wie im Chat
        # (SOUL.md der Installation, sonst die mitgelieferte Vorlage), dann ihre Akte
        # als Zusatz für die Firma. Zusammengesetzt wird nur hier, die Akte selbst
        # enthält nur den Zusatz (sonst stünde er nach dem Speichern doppelt da).
        eigen = cfg.persona_read("soul").strip()
        if eigen:
            soul = eigen + "\n\n" + soul
    teile = [soul]
    stil = ag.style_read().strip()
    if stil:
        teile.append(stil)
    if a.get("memory", "").strip():
        teile.append(cfg.L("## Was du dir gemerkt hast\n\n", "## What you have remembered\n\n")
                     + a["memory"].strip())
    hist = ag.historie_text(a["slug"])
    if hist:
        teile.append(hist)
    nutzer = ag.user_read().strip()
    if nutzer:
        teile.append(cfg.L("## Was die Firma über den Nutzer weiß\n\n",
                           "## What the company knows about the user\n\n") + nutzer)
    # Die Bus-Regeln der Auftragsarbeit.
    proto = ag.protocol_read().strip()
    if proto:
        teile.append(proto)
    # Was "gut aussehen" heisst. Auch fuer die, die nicht selbst gestalten:
    # die Geschaeftsfuehrung muss den Schritt einplanen, der Pruefer muss
    # ihn beurteilen koennen.
    gest = ag.gestaltung_read().strip()
    if gest:
        teile.append(gest)
    # Mit dem, was jeder KANN — nicht nur, wer er ist. Wer Screenshots, Builds
    # oder Tests vergibt, muss sehen, wer eine Shell hat (s. ag.faehigkeiten).
    teile.append(cfg.L("Du arbeitest in einer Firma aus KI-Mitarbeitern. Die Belegschaft:\n",
                       "You work in a company of AI employees. The staff:\n")
                 + "\n".join(f"- {x['slug']} = {x['name']}, {x['title']} ({ag.faehigkeiten(x)})"
                             for x in ag.list_agents(workspace) if x["slug"] != a["slug"])
                 + cfg.L("\nBeim Beauftragen und Fragen benutzt du den slug, nicht den Namen. "
                         "Arbeit, die eine Shell braucht, geht nur an jemanden mit Shell.",
                         "\nWhen briefing or asking, use the slug, not the name. "
                         "Work that needs a shell only goes to someone with a shell."))
    # Nur der INDEX der Anleitungen — Name und Anlass, nicht der Inhalt. Den
    # holt sich ein Mitarbeiter ueber das Werkzeug `anleitung`, wenn die Lage
    # passt. Zwanzig Anleitungen kosten so rund 1200 Zeichen statt 40 000.
    idx = anl.index()
    if idx:
        teile.append(idx)
    # Was der Nutzer selbst geschrieben hat (USER.md), bleibt wörtlich.
    return ag.anrede("\n\n---\n\n".join(teile), roh=(nutzer,))
