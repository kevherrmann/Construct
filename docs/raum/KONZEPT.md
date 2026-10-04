# Der Construct-Raum — Konzept

Stand: 04.10.2026

## Die Idee in einem Satz

Eine zweite Ansicht neben dem Chat: der weiße Raum aus dem Film, in dem man
dieselbe Arbeit nicht liest, sondern **sieht**. Und alles, was im Chat geht,
geht auch hier (außer den Einstellungen), nur anders.

## Grundsätze

1. **Gleiche Logik, andere Bühne.** Der Raum nutzt dieselben Stores und Hooks
   wie der Chat (`useChat`, Sessions, Kalender, Mail, Skills). Nichts wird
   doppelt gebaut. Was im Chat funktioniert, funktioniert im Raum automatisch,
   und ein Fehler wird an einer Stelle behoben.
2. **Umschaltbar, nie aufgezwungen.** Standard bleibt der Chat. Ein Schalter in
   der Kopfzeile wechselt `Chat ⇄ Raum`, die Wahl wird gemerkt. Eine laufende
   Antwort läuft beim Umschalten weiter.
3. **Kein Spielzeug.** Der Raum muss bedienbar sein wie ein Werkzeug: jede
   Station hat eine klare Aufgabe, jeder Klick führt zu einer echten Funktion.
   Effekte nur, wo sie etwas erzählen (Cody liest gerade, ein Befehl läuft).
4. **Lieber leer als überladen.** Der Film-Raum ist fast leer. Das ist der
   Reiz: wenige, ruhige Stationen, viel Weiß, ein Akzent in der Farbe der
   gewählten Farbwelt.
5. **Läuft überall.** 2.5D, keine 3D-Engine, kein WebGL. Ein gemaltes Raumbild,
   darauf Figur und Lichtakzente als Ebenen. Im Sparmodus (Desktop-App mit
   Software-Rendering) Standbilder mit Überblendung statt Videos.

## Bildsprache

- **Stil:** halbrealistisch gemalt, Konzeptkunst mit sichtbarem Pinselstrich.
  Die Figur wird in genau diesen einen Stil übersetzt, Gesicht und
  Ausstrahlung bleiben erkennbar.
- **Raum:** wirklich weiß, weiches Licht, kaum Schatten, fast leer. Isometrisch
  leicht von oben, man überblickt alles.
- **Akzent:** Die Figuren tragen einen feinen Lichtsaum, Stationen leuchten bei
  Aktivität, beides in der Akzentfarbe der Farbwelt (Matrix-Grün als Vorgabe).
- **Typografie:** dünn, viel Luftraum, dunkelgrau auf Weiß. Keine Terminal-
  Optik im Raum, die gehört in den Chat.
- **Keine Fenster:** Ein Klick auf eine Station fährt die Kamera heran
  (`kamera.ts`, Zoom + Verschiebung der Welt). Die andere Seite des Raums
  läuft ins Weiß des Construct aus, dort steht der Inhalt, nur so breit wie
  nötig, mit Lichtkante und einer feinen Leitlinie zur Station
  (`AUFTRITT` in `stationen.ts`).
- **Terminal auf dem Fernseher:** Befehle laufen live auf der Monitorwand
  (perspektivisch per `matrix3d`, per Maske auf die Bildschirme zugeschnitten).
- **Monitor = Tür zur Chat-Ansicht:** Ein Klick fährt die Kamera in die
  Bildschirme, bis sie alles füllen, ein Vorhang in der Farbe der Farbwelt
  schließt sich, dann kommt die Chat-Ansicht. Wer den Raum betritt, kommt
  umgekehrt aus dem Monitor heraus.
- **Protokoll** liegt als Klemmbrett auf der Werkbank (Klick = Verlauf).
- **Sprechzeile statt Chat-Leiste:** Die Eingabe schwebt als Lichtlinie über
  dem Boden. Ordner, Modus und Modell liegen an Regal und Pult; deren Schilder
  zeigen die aktuelle Wahl.
- **Werkbank und Fernseher** lesen Dateien und Befehle der ganzen Session
  vom Server (`/api/werkstatt/<id>`, aus dem Protokoll; der geladene Verlauf
  kennt nur Text). Die Werkbank zeigt dazu die offenen git-Änderungen, also
  auch, was per Befehl geändert wurde.
- **Hover, je nach Leistung:** im Sparmodus ein weicher Lichthof um das
  Objekt (`assets/schein/`, billig); mit voller Optik stellt die Kamera auf das Objekt scharf: der Rest des Raums
  wird unscharf und tritt ins Weiß zurück (unscharfe Raumfassung + Maske
  „alles außer der Station“ aus `assets/form/`). Kein Kasten, kein Schild
  beim Arbeiten (der Status steht in der Blase).
- **Kontingent an der Wand:** links neben der Uhr, über der Lochwand, steht
  wie viel vom Claude-Kontingent (5 Stunden, Woche) verbraucht ist, mit
  Reset-Zeit, als Schrift im Winkel der Wand (`WAND_KONTINGENT`).
- **Kleinigkeiten:** Die Wanduhr geht richtig (Zeiger per SVG auf dem
  Zifferblatt, gemalte Zeiger wegretuschiert); aus der Nähe zeigt sie eine
  Digitaluhr mit dem Tag als Zeitleiste und dem nächsten Termin. Der
  Projektname steht unter dem Regal im Winkel der Regalfront (flache
  `matrix`, weil WebKitGTK ohne 3D-Ebenen die Perspektive von `matrix3d`
  ignoriert). Der Fernseher ist per Maske genau auf die gebogenen
  Bildschirme zugeschnitten.
- **Sprechblase in Abschnitten:** wie Untertitel immer nur ein Abschnitt
  (`abschnitte()` in `lage.ts`), beim Sprechen der jüngste, mit ‹ › blättern;
  alles am Stück im Verlauf.
- **Sprechblase:** Klick auf die Figur blendet sie aus und ein; zu gilt nur
  für die aktuelle Antwort. Zu, aber Text da: drei Punkte über dem Kopf.

## Die Stationen

| Station | Im Raum | Funktion (wie im Chat) | Zeigt Aktivität |
|---|---|---|---|
| **Cody** | Mitte, steht am Pult | Gespräch: Nachricht senden, Bild anhängen, Diktat, Stopp, Einwerfen, Warteschlange | Pose: wartet, hört zu, denkt nach, arbeitet |
| **Sprechtafel** | schwebt neben der Figur | letzte Antwort als Markdown (Code als Chip, Tabellen, Bilder), scrollbar, läuft beim Streamen mit | Text erscheint beim Streamen |
| **Protokoll** | Rolle/Schriftstück am Pult | ganzer Verlauf der Session zum Nachlesen | – |
| **Regalwand** | links hinten | Projekte = Arbeitsordner wählen, Unterordner | leuchtet, wenn Dateien gelesen werden; Dateiname schwebt kurz auf |
| **Archiv** | Schrank neben dem Regal | Sessions: neu, öffnen, suchen, umbenennen, archivieren, löschen | – |
| **Bildschirmwand** | rechts hinten | Terminal: laufende und letzte Befehle mit Ausgabe | Befehl tippt sich ein, Ausgabe läuft |
| **Werkbank** | rechts | geänderte Dateien dieser Session, anklickbar (Vorschau) | glimmt, wenn geschrieben wird |
| **Werkzeugwand** | an der Werkbank | Skills ansehen | Skill leuchtet, wenn er benutzt wird |
| **Steckfeld** | klein, an der Wand | MCP-Server und Status | Stecker leuchtet bei MCP-Aufruf |
| **Wanduhr / Wandkalender** | Wand rechts | Kalender: Monat, Termine anlegen und ändern, Tagebuch | nächster Termin als kleine Notiz |
| **Postfach** | vorne links | E-Mail: lesen, schreiben, antworten, sortieren, löschen | Zähler ungelesener Mails |
| **Ladestation** | am Pult | Modell, Modus, Aufwand („welches Programm wird geladen“) | – |

Hintergrundjobs: ein ruhiges Leuchten in einer Ecke, solange sie laufen.
Sub-Agenten: weitere, halbtransparente Figuren, die kurz auftauchen.

## Technik

- **Ansicht:** neuer Modus über dem bestehenden `AppShell`. Topbar bleibt, die
  Seitenleiste fällt weg, der Raum füllt die Fläche. Bühne in festem 16:9,
  per `contain` skaliert, Stationen als Flächen in Prozent-Koordinaten.
- **Paneele:** Stationen öffnen Glaskarten. Erste Ausbaustufe nutzt darin die
  vorhandenen Komponenten (Sessions, Kalender, Mail …) in einer hellen
  Raum-Variante. Später bekommen die wichtigsten eigene Raum-Oberflächen.
- **Aktivität:** Die Stream-Ereignisse (`tool` mit Name und Eingabe,
  `tool_result`, `text`, `thinking_marker`, `nachlauf`, `done`) werden auf
  Stationen und Posen abgebildet, in einer eigenen kleinen Zuordnung
  (`raum/choreo.ts`), testbar ohne Oberfläche.
- **Figur:** je Pose ein freigestelltes Bild (PNG/WebP), später kurze
  Video-Schleifen. Im Raum steht Cody; eine Installation kann ihn durch eine
  eigene Figur ersetzen (`static/figur/`, gitignored, Dateinamen in
  `RaumView.tsx` bei `eigeneFigur`).
- **Entwicklung:** in der Demo-Installation (`~/projects/construct-demo`). Das
  Fake-`claude` spielt dort wiederholbar Sitzungen ab, mit Dateien lesen,
  Befehlen und Schreiben.

## Ausbaustufen

1. ✅ **Bild:** Raum und eine Pose der Figur. Abweichung vom
   ersten Plan: Der Raum kam als sauberes, weiches Rendering statt gemalt —
   das passt besser zum Film, die Figuren wurden danach ausgerichtet.
2. ✅ **Gerüst:** Umschalter (Kopfzeile ⇄ Raum), Bühne 16:9, Stationen
   anklickbar, Figur steht.
3. ✅ **Gespräch:** echte Eingabe als Pult unten, Sprechblase mit Status,
   Protokoll-Leiste mit dem echten Verlauf.
4. ✅ **Stationen:** Sessions, Projekte, Kalender, Mail, Skills, MCP mit den
   vorhandenen Bausteinen (hell über die Variablen der Farbwelt); Terminal,
   Werkbank und „Modell & Modus“ als eigene Übersichten.
5. ✅ **Choreografie:** `lage.ts` bildet Ereignisse auf Station, Pose und
   Statuszeile ab (getestet); aktive Station leuchtet und zeigt, was passiert.
6. ✅ **Bewegung:** vier Posen am Podest (ruhig, nachdenken, lesen, erklären)
   mit Überblendung und Mindestdauer. Video-Schleifen (Kling 2.6, über
   `construct-raum-art/clip.py` aufbereitet) für ruhig (nur Atmen, 5 s,
   nahtlos über Start- = Endbild), nachdenken und lesen (Ping-Pong, 10 s) und
   tippen an der Werkbank (5 s). Jede Schleife hat eine Maske in Figurform
   (`assets/video/<figur>-<pose>-maske.webp`), damit Fernseher, Klemmbrett
   und Hover-Unschärfe drumherum unberührt bleiben. Kurzes Nachdenken zwischen
   zwei Werkzeugen holt die Figur nicht von der Werkbank weg (2,5 s halten).
   Im Sparmodus „aus“ oder wenn ein Video nicht startet: Standbild mit
   leichtem Atmen. *Offen:* Schleife für „erklären“.
7. ◐ **Feinschliff:** Hinweis auf kleinen Bildschirmen, Englisch, WebKitGTK
   geprüft. *Offen:* Komponententest, README/Video-Szene, Rückmeldung aus dem Test.

Arbeitsdateien (Bildgenerierung, Freisteller, Stationsmaße):
`~/projects/construct-raum-art/` (außerhalb des Repos).
