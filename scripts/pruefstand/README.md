# Der Prüfstand

Feste Aufträge gegen die Firma des Team-Modus, damit „ist es dadurch besser geworden?"
eine Antwort mit Zahlen hat statt eines Bauchgefühls.

Gebraucht wird er nach jeder Änderung an etwas, das **Verhalten** steuert:
`PROTOCOL.md`, `HAUSSTIL.md`, eine `SOUL.md`, die Grenzen in `server/team/guards.py`,
ein Modellwechsel in einer `AGENT.md`.

```
python3 scripts/pruefstand.py lauf                    alle Fälle (startet CONSTRUCT auf Port 8798, falls nötig)
python3 scripts/pruefstand.py lauf --nur smoke        nur passende
python3 scripts/pruefstand.py lauf --budget 1.00      abbrechen, bevor es teuer wird
python3 scripts/pruefstand.py lauf --faelle faelle-factoria   dieselben Fälle wie in FACTORIA
python3 scripts/pruefstand.py liste                   welche Fälle es gibt
python3 scripts/pruefstand.py vergleich               letzter Lauf gegen den davor
python3 scripts/pruefstand.py aufraeumen              Testaufträge und Arbeitsordner weg
python3 scripts/pruefstand.py firma-vorbereiten --aus ~/projects/factoria
```

**Die Firma, an der gemessen wird, ist eine Kopie** (`scripts/pruefstand/firma/`, nicht im Git).
Ohne `firma-vorbereiten` baut sie sich beim ersten Start aus den mitgelieferten Vorlagen auf
(Chef, Entwickler, Prüfer); mit `--aus` übernimmt sie eine bestehende Belegschaft samt
Regelwerken — dann misst derselbe Fall dieselben Mitarbeiter mit denselben Regeln, und ein
Unterschied zum früheren Lauf kommt aus dem Programm, nicht aus den Daten. Der Prüfstand
startet dazu einen eigenen Server (`CONSTRUCT_FIRMA_DIR`, `CONSTRUCT_TEAM=1`); die laufende
Installation bleibt unberührt.

Jeder Lauf vergleicht sich am Ende von selbst mit dem davor. Das ist der Punkt:
nicht „besteht der Fall", sondern **„besteht er noch, seit ich etwas geändert
habe"**. Ein Rückschritt wird ausdrücklich als solcher gemeldet.

Der Rückgabewert ist 1, sobald ein Fall durchfällt — brauchbar für ein Skript,
das vor dem Commit prüft.

## Einen Fall schreiben

Eine Datei in `faelle/`. Vorne die Soll-Werte, dahinter der Auftrag in den Worten
des Nutzers. Was im Frontmatter nicht dasteht, wird nicht geprüft.

```markdown
---
titel: Wofür der Fall da ist
owner: entwickler      wer den Auftrag bekommt (Slug); Vorgabe chef
erwartet: fertig       fertig | wartet_auf_kevin | abgebrochen
bremse: keine          keine, oder der Name der Bremse, die fallen SOLL
max_hops: 3            Züge
max_kosten: 0.40       Dollar
max_nachricht: 1000    längste Bus-Nachricht; Vorgabe 1000 (PROTOCOL.md), 0 = aus
timeout: 300           Sekunden, dann gilt der Fall als hängengeblieben
dateien: bericht.md    muss danach im Arbeitsordner liegen
gemeldet: bericht.md   muss im Feld `dateien` abgeliefert worden sein
enthaelt: 5472661      Stichworte, die im Ergebnistext stehen müssen
agenten: chef, entwickler  wer beteiligt gewesen sein muss
agenten_einer: pruefer   mindestens einer davon (Wahl liegt bei der Firma)
---
Der Auftrag, wie Kevin ihn stellen würde.
```

Jeder Fall arbeitet in `scripts/pruefstand/arbeit/<name>/`, und der wird vor jedem Lauf leer
geräumt — sonst besteht ein Fall irgendwann, weil die Datei von gestern noch
dalag.

## Was hier absichtlich fehlt

**Kein Modell als Schiedsrichter.** Ein zweites Sprachmodell, das Noten
verteilt, kostet, schwankt zwischen zwei Läufen und misst am Ende sich selbst.
Geprüft wird nur, was hart nachweisbar ist: Zustand, Zahlen, Dateien,
Stichworte. Lässt sich ein Fall so nicht prüfen, ist er schlecht geschnitten
und gehört umgeschrieben — nicht mit einem Richtermodell zugedeckt.

**Kein Anspruch auf Vollständigkeit.** Vier gute Fälle, die man wirklich laufen
lässt, sind mehr wert als dreißig, die zu teuer sind, um sie anzufassen. Ein
neuer Fall lohnt sich, wenn er etwas prüft, das schon einmal kaputtgegangen ist.

## Warum nach dem Ende noch gewartet wird

Ein Auftrag steht auf `fertig`, sobald jemand `liefern` aufruft — mitten im
laufenden Zug. Die **Kosten** bucht der Server aber erst, wenn der
`claude`-Prozess wirklich beendet ist (`_ende`), und dazwischen liegen ein paar
Sekunden.

Wer im Moment des Statuswechsels misst, bekommt denselben Fall einmal mit
0,0000 $ und einmal mit 0,1139 $ — je nachdem, wie der Poll fällt. Genau das
ist beim ersten echten Lauf passiert. Eine Zahl, die ohne Zutun schwankt, macht
den Lauf-Vergleich wertlos, weil sie Rückschritte meldet, die es nicht gibt.

`nachfassen()` wartet deshalb, bis kein Zug mehr läuft und die Kosten sich
zwischen zwei Abfragen nicht mehr ändern. Kommt trotzdem keine Zahl an, obwohl
es Züge gab, meldet der Prüfstand das als **nicht geprüft** (`?`) — nicht als
bestanden.
