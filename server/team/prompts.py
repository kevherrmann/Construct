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
from server.team import agents as ag
from server.team import anleitungen as anl
from server.team import auftraege as auf
from server.team import guards


def auftrags_prompt(a: dict, t: dict, nachricht: dict) -> str:
    """Die NACHRICHT des Zuges — alles Veraenderliche gehoert hierher.

    Auftragslage und die eigentliche Nachricht aendern sich bei jedem Zug.
    Stuende das im Systemprompt, waere dessen Zwischenspeicher jedes Mal
    wertlos — im Direktgespraech hat genau diese Trennung den zweiten Zug
    achtmal billiger gemacht.

    Der Zaehlerstand der Bremsen steht hier BEWUSST nicht drin: wer bei jedem
    Zug liest, wie viel er noch darf, plant danach statt zu arbeiten. Erst wenn
    es wirklich eng wird, kommt ein Satz dazu.
    """
    kopf = [
        f"# Auftrag: {t['titel']}",
        f"Kevins Worte: {t['brief']}",
    ]
    rest = guards.rest_schritte(t, auf.verlauf(t["id"]))
    if rest <= guards.WARNUNG_AB:
        kopf.append(f"Achtung: noch {rest} Schritte, dann haelt der Auftrag an und Kevin muss "
                    f"ran. Liefere lieber ein ehrliches Teilergebnis mit dem, was fehlt.")
    if t.get("artefakte"):
        kopf.append("Bisher angefasste Dateien: "
                    + ", ".join(x["pfad"] for x in t["artefakte"][-8:]))
    offen = ausstehend(a["slug"], auf.verlauf(t["id"]))
    if offen and nachricht.get("art") != "auftrag":
        kopf.append("Von dir beauftragt und noch ohne Ergebnis: " + ", ".join(offen))
    # Was schon im Postfach liegt, aber erst im naechsten Zug kommt. Ohne den
    # Satz sagte Lumina am 11.09.2026 "ich warte auf Tessa", waehrend Tessas
    # Ergebnis laengst da war — nur hinter Raukes in der Reihe.
    liegt = [n for n in auf.offene_nachrichten(t["id"])
             if n.get("an") == a["slug"] and n.get("id") != nachricht.get("id")]
    if liegt:
        kopf.append("Liegt schon für dich bereit und kommt im nächsten Zug von selbst "
                    "(nicht darauf warten, nicht danach fragen): "
                    + ", ".join(f"{n.get('art')} von {n.get('von')}" for n in liegt))
    absender = nachricht.get("von") or "kevin"
    wer = "Kevin" if absender == "kevin" else absender
    art = {"auftrag": "beauftragt dich", "frage": "fragt dich",
           "antwort": "antwortet dir", "ergebnis": "liefert dir"}.get(nachricht.get("art"), "schreibt dir")
    kopf.append(f"\n## {wer} {art}:\n\n{nachricht.get('text', '')}")
    kopf.append("\n" + zug_abschluss(a, t, nachricht))
    return ag.anrede("\n".join(kopf))


def zug_abschluss(a: dict, t: dict, nachricht: dict) -> str:
    """Der letzte Satz vor dem Handeln: womit dieser Zug enden muss.

    Warum das hier steht, obwohl PROTOCOL.md es laengst sagt: dort ist es Punkt
    fuenf einer Liste, und danach kommen noch zwei Dokumente. Gelesen wird es,
    befolgt nicht. Der Pruefstand hat am 03.09.2026 an zwei von vier Faellen
    gezeigt, wie das ausgeht — Lumina fasst ein fertiges Ergebnis korrekt
    zusammen und ruft `liefern` nicht auf, Chanti stellt eine gute Rueckfrage
    und ruft `eskalieren` nicht auf. Inhaltlich beide richtig, nur nie am Bus
    angekommen; die Notbremse `stiller_zug` holt dann Kevin zu einem Auftrag,
    der eigentlich fertig war.

    Deshalb steht die Regel zusaetzlich als LETZTE Zeile der Nachricht, direkt
    vor dem Handeln. Und sie zaehlt nicht alle Werkzeuge auf, sondern die ein
    bis zwei, die in dieser Lage richtig sind — eine Liste mit allen ist wieder
    nur Protokoll zum Ueberlesen.
    """
    schluss = "Ein Zug ohne Bus-Aufruf haelt den ganzen Auftrag an."
    art = nachricht.get("art")

    if art == "frage":
        return f"**Beende deinen Zug mit `antworten`.** {schluss}"

    if art == "ergebnis" and a["slug"] == t["owner"]:
        # Der heikelste Fall: der Auftrag ist faktisch fertig, und genau hier
        # blieb er im Pruefstand liegen.
        offen = ausstehend(a["slug"], auf.verlauf(t["id"]))
        if offen:
            return ("**Du fuehrst diesen Auftrag.** Es arbeiten noch: "
                    + ", ".join(offen) + ". Warte deren Ergebnis ab, bevor du "
                    "lieferst — `notiz`, wenn du dir etwas festhalten willst, "
                    f"sonst vergib den naechsten Schritt. {schluss}")
        return ("**Du fuehrst diesen Auftrag.** Pruefe, ob er damit erledigt "
                "ist — wenn ja, `liefern` (das geht an Kevin und schliesst den "
                f"Auftrag ab). Wenn nicht, vergib den naechsten Schritt. {schluss}")

    if art == "auftrag" and nachricht.get("groesse") == "klein":
        # Der Umsetzer schreibt hier fuer Kevin, nicht fuer die
        # Geschaeftsfuehrung — die liest sein Ergebnis nicht mehr.
        return ("**Das ist ein Kleinauftrag: dein `liefern` geht direkt an Kevin "
                "und schliesst den Auftrag ab.** Schreib das Ergebnis also fuer ihn — "
                "was jetzt anders ist, was er wissen muss. Kommst du ohne ihn nicht "
                f"weiter: `eskalieren`. {schluss}")

    if art in ("auftrag", "antwort") and a.get("can_delegate"):
        # Wer verteilen darf, soll das auch tun. Stand hier frueher nur
        # "liefern oder eskalieren", war das eine Einladung an die
        # Geschaeftsfuehrung, es doch schnell selbst zu machen.
        return ("**Beende deinen Zug mit `beauftragen`** (du gibst die Arbeit "
                "an den Richtigen weiter — unabhaengige Teile auch an mehrere), "
                "**`liefern`** (nichts zu verteilen, dein Teil steht) **oder "
                f"`eskalieren`** (du kommst ohne Kevin nicht weiter). {schluss}")

    return ("**Beende deinen Zug mit `liefern`** (dein Teil steht) **oder "
            f"`eskalieren`** (du kommst ohne Kevin nicht weiter). {schluss}")


def ausstehend(slug: str, verlauf: list) -> list:
    """Wen dieser Mitarbeiter beauftragt hat, ohne bisher ein Ergebnis zu haben.

    Gebraucht, seit ein Verteiler mehrere Leute in EINEM Zug beauftragen darf:
    kommt das erste Ergebnis herein, muss er wissen, dass noch eines fehlt —
    sonst liefert er an Kevin, waehrend Selma noch an der Oberflaeche sitzt.
    """
    offen = []
    for e in verlauf:
        if e.get("art") == "auftrag" and e.get("von") == slug and e.get("an"):
            if e["an"] not in offen:
                offen.append(e["an"])
        elif e.get("art") == "ergebnis" and e.get("an") == slug and e.get("von") in offen:
            offen.remove(e["von"])
    return offen


def agent_system_prompt(a: dict, workspace, auftrag: bool = False) -> str:
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
    soul = (a.get("soul") or f"Du bist {a['name']}, {a['title']}.").replace("{name}", a["name"])
    teile = [soul]
    stil = ag.style_read().strip()
    if stil:
        teile.append(stil)
    if a.get("memory", "").strip():
        teile.append("## Was du dir gemerkt hast\n\n" + a["memory"].strip())
    hist = ag.historie_text(a["slug"])
    if hist:
        teile.append(hist)
    nutzer = ag.user_read().strip()
    if nutzer:
        teile.append("## Was die Firma über den Nutzer weiß\n\n" + nutzer)
    if auftrag:
        # Nur in der Auftragsarbeit: die Bus-Regeln. Im Direktgespraech waeren
        # sie falsch — dort gibt es keinen Bus und keine Bremsen.
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
    teile.append("Du arbeitest in einer Firma aus KI-Mitarbeitern. Die Belegschaft:\n"
                 + "\n".join(f"- {x['slug']} = {x['name']}, {x['title']} ({ag.faehigkeiten(x)})"
                             for x in ag.list_agents(workspace) if x["slug"] != a["slug"])
                 + "\nBeim Beauftragen und Fragen benutzt du den slug, nicht den Namen. "
                 "Arbeit, die eine Shell braucht, geht nur an jemanden mit Shell.")
    # Nur der INDEX der Anleitungen — Name und Anlass, nicht der Inhalt. Den
    # holt sich ein Mitarbeiter ueber das Werkzeug `anleitung`, wenn die Lage
    # passt. Zwanzig Anleitungen kosten so rund 1200 Zeichen statt 40 000.
    idx = anl.index()
    if idx:
        teile.append(idx)
    return ag.anrede("\n\n---\n\n".join(teile))
