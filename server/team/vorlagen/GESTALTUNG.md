# Gestaltung — was hier „gut" heißt

Gilt für alles, was Kevin am Bildschirm ansieht: Seiten, Oberflächen, Ausgaben.
Der Hausstil regelt, wie wir schreiben — hier steht, wie es aussehen muss.

## Urteile am Bild

Mach einen Screenshot und sieh ihn dir an. Der Code sagt dir, was du gemeint
hast; das Bild sagt dir, was herausgekommen ist.

**Wenn du es selbst nicht zeigen würdest, ist es nicht fertig.** „Alle Werte
stimmen" ist kein Urteil: 17:1 Kontrast auf einer hässlichen Seite ergibt eine
hässliche Seite mit gutem Kontrast.

## Zwei Durchgänge, mindestens

Bauen → ansehen → überarbeiten. Wer nach dem ersten Durchgang liefert, hat nicht
hingesehen. Im zweiten Durchgang suchst du keine Fehler, sondern beantwortest
eine Frage: **Würde ich das jemandem zeigen, dessen Urteil mir wichtig ist?**

## Referenz heißt ansehen

Steht im Auftrag „soll aussehen wie X", dann öffne X und sieh es dir an.
Farbwerte aus einer Datei abzuschreiben ist keine Gestaltung — die Anmutung
steckt in Abständen, Dichte, Typografie und Bewegung, nicht in `#00ff41`. Leg
dein Ergebnis und die Referenz nebeneinander, bevor du lieferst.

## Nichts liegt über dem Inhalt

Effekte gehören **dahinter**: Hintergrund, Verlauf, Muster, Regen. Nichts davon
darf über Text oder Bildern liegen, und nichts darf Lesbarkeit kosten. Ein
Effekt, der die Schrift schwerer lesbar macht, ist kein Effekt, sondern ein
Fehler. Alles Bewegte ist abschaltbar und respektiert `prefers-reduced-motion`.

## Der Leerzustand ist ein Zustand

Fehlt ein Bild, **tritt etwas an seine Stelle**: Typografie, Initial, ein Muster
mit dem Titel. Nie eine leere Fläche — leere Kästen sehen nicht minimalistisch
aus, sondern kaputt.

Ist die ganze Liste leer, ist das Beste an dieser Stelle meist **die Form des
Eintrags, der hier hinkommt**: die Zeile als angedeutete Balken, gestrichelt
umrandet, darunter ein Satz und der eine Knopf. Das erklärt ohne Text, was die
Seite kann. Ein großes Symbol tut das nicht — es sieht im Zweifel aus wie ein
Glyph, den der Rechner nicht darstellen kann.

Prüfe jede Ansicht in drei Fällen, immer:

- **kein Eintrag** — sagt die Seite freundlich, dass hier noch nichts ist?
- **ein Eintrag** — wirkt sie dann leer und verloren?
- **zwanzig Einträge** — wird sie unübersichtlich, muss man ewig scrollen?

Eine Ansicht, die nur mit genau sechs Einträgen funktioniert, ist nicht fertig.

## Das Medium bestimmt die Darstellung

Nicht alles ist eine Kachel mit Bild.

- **Musik** ist eine Liste: Titel, Dauer, Abspielknopf. Ein Song ohne Bild
  braucht kein Bild, er braucht einen Knopf.
- **Bilder** wollen Fläche und wenig Rahmen. Beschnitt nie mitten durch das
  Motiv oder durch Schrift.
- **Text** will Zeilenlänge — etwa 70 Zeichen, nicht die volle Fensterbreite.
- **Code und Pfade** wollen Monospace und Umbruch, keine Ellipse.

Wer alles in dieselbe Kachel presst, hat die Sache nicht verstanden.

## Rahmen nur da, wo man klickt

Ein Kästchen um eine Angabe sieht nach Schalter aus. In einer Liste mit zwanzig
Einträgen werden aus hübschen Schlagwort-Chips vierzig graue Rechtecke, und die
Liste flimmert. Dieselbe Angabe bekommt einen Rahmen, wenn sie **Bedienelement**
ist (Filter, Knopf) — und keinen, wenn sie nur dasteht. Das kostet nichts und
beruhigt eine Ansicht mehr als jede Farbkorrektur.

## Zu wenig Material ist ein Befund

Erfinde keine Inhalte — aber liefere auch keine Platzhalter-Wüste. Reicht das
Material für eine Sektion nicht, sag es Kevin, statt drei leere Kacheln
hinzustellen. Drei gute Einträge schlagen zehn halbe.

## Messen kommt zuletzt

Pflicht, nicht Kür: Kontrast mindestens 4,5:1 für Text und 3:1 für
Bedienelemente, sichtbarer Fokusring auf allem Bedienbaren, alles per Tastatur
erreichbar, kein waagerechtes Scrollen bei 320 px Breite, Bilder mit `alt`.

Gemessen wird am laufenden Ergebnis im Browser, nicht an den Variablen im
Quelltext. Und Messwerte ersetzen kein Urteil — sie sind die Untergrenze.

**Eine Rahmenfarbe ist keine Textfarbe.** Für Umrisse reichen 3:1, für Text nicht
— wer denselben Grauton für beides nimmt, hat die Hälfte seiner Beschriftungen
unter der Grenze. Dafür gehört eine eigene Stufe in die Tokens: die leiseste
Farbe, die noch **Text** sein darf.
