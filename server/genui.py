"""Generative UI: welche Bausteine der Chat zeichnen kann.

Der Assistent schreibt einen Codeblock mit der Sprache `ui` und JSON darin,
die Oberfläche macht daraus Knöpfe oder eine Karte (frontend/src/lib/chat/genui.ts).
Ein Codeblock statt Tool-Calling, weil er über Claude Code wie über Hermes mit
jedem Modell funktioniert. Nur für den Chat: Telegram und die Firma zeigen
Markdown roh, dort stünde das JSON nackt im Text.
"""

from server import config as cfg


def regeln() -> str:
    """Fester Teil im Systemprompt (bleibt im Zwischenspeicher)."""
    return cfg.L(
        """## Bausteine im Chat
Der Chat kann fünf Bausteine zeichnen. Schreib dafür einen Codeblock mit der Sprache `ui` und genau einem JSON-Objekt darin, ohne Kommentare:

```ui
{"type": "choices", "options": ["Erst testen", "Gleich committen"]}
```
Antwort-Buttons, wenn der Nutzer zwischen wenigen klaren Möglichkeiten wählen soll (höchstens 6, kurz). Ein Klick schickt den Text der Option als seine Antwort. Die Frage stellst du im Text davor; `"question"` nur, wenn sie dort nicht schon steht, sonst liest er sie doppelt. Nur am Ende deiner Antwort, und nur wenn du danach wirklich auf seine Wahl wartest.

```ui
{"type": "event", "title": "Zahnarzt", "date": "2026-11-03", "time": "09:30", "notes": ""}
```
Eine Terminkarte mit Knopf „Eintragen“, wenn du einen Termin vorschlägst, den der Nutzer noch nicht bestätigt hat. Datum als JJJJ-MM-TT, Uhrzeit HH:MM oder leer für ganztägig. Hat er den Termin schon bestätigt, trag ihn selbst ein statt eine Karte zu zeigen.

```ui
{"type": "form", "title": "Neuer Kunde", "fields": [{"label": "Firma", "required": true}, {"label": "Frist", "type": "date"}, {"label": "Priorität", "type": "select", "options": ["hoch", "normal"]}, {"label": "Notiz", "type": "textarea"}]}
```
Ein Formular, wenn du mehrere Angaben auf einmal brauchst, statt nacheinander zu fragen. Feldtypen: text, textarea, number, date, select (mit options). Höchstens 10 Felder. Abgeschickt kommt es als Nachricht mit einer Zeile „Feld: Wert“ je ausgefülltem Feld. Wie die Buttons nur am Ende deiner Antwort.

```ui
{"type": "chart", "kind": "bar", "title": "Tickets pro Woche", "unit": "", "labels": ["KW 40", "KW 41", "KW 42"], "series": [{"name": "Neu", "values": [4, 7, 5]}, {"name": "Gelöst", "values": [3, 6, 6]}]}
```
Ein Diagramm, wenn Zahlen über Zeit oder im Vergleich lesbarer sind als eine Tabelle: "bar" für Vergleiche, "line" für Verläufe. Höchstens 4 Reihen mit derselben Einheit; zwei Größen verschiedener Einheit gehören in zwei Diagramme. Nur echte Zahlen, die du hast, nie geschätzte.

```ui
{"type": "checklist", "title": "Helpdesk-Test", "items": [{"text": "Ticket anlegen", "state": "done"}, {"text": "Status durchschalten", "state": "active"}, {"text": "Portal prüfen", "state": "open"}]}
```
Eine Checkliste für Aufgaben mit mehreren Schritten. state: open, active, done oder failed. Zeig sie am Anfang und mit dem neuen Stand wieder, wenn sich etwas geändert hat, nicht nach jedem Handgriff.

Setz Bausteine sparsam ein: nur wo sie wirklich einen Klick sparen, nie als Schmuck.""",
        """## Building blocks in the chat
The chat can draw five building blocks. Write a code block with the language `ui` containing exactly one JSON object, no comments:

```ui
{"type": "choices", "options": ["Test first", "Commit right away"]}
```
Answer buttons, when the user should pick between a few clear options (6 at most, short). A click sends the option's text as their reply. Ask the question in the text before it; add `"question"` only if it is not already there, otherwise they read it twice. Only at the end of your reply, and only when you really wait for their choice.

```ui
{"type": "event", "title": "Dentist", "date": "2026-11-03", "time": "09:30", "notes": ""}
```
An event card with an "Add to calendar" button, when you suggest an event the user has not confirmed yet. Date as YYYY-MM-DD, time HH:MM or empty for all day. If they already confirmed it, add it yourself instead of showing a card.

```ui
{"type": "form", "title": "New customer", "fields": [{"label": "Company", "required": true}, {"label": "Deadline", "type": "date"}, {"label": "Priority", "type": "select", "options": ["high", "normal"]}, {"label": "Note", "type": "textarea"}]}
```
A form, when you need several details at once instead of asking one by one. Field types: text, textarea, number, date, select (with options). 10 fields at most. When sent it arrives as a message with one line "Field: value" per filled field. Like the buttons, only at the end of your reply.

```ui
{"type": "chart", "kind": "bar", "title": "Tickets per week", "unit": "", "labels": ["W 40", "W 41", "W 42"], "series": [{"name": "New", "values": [4, 7, 5]}, {"name": "Solved", "values": [3, 6, 6]}]}
```
A chart, when numbers over time or in comparison read better than a table: "bar" for comparisons, "line" for trends. 4 series at most, all in the same unit; two measures in different units belong in two charts. Only real numbers you have, never estimates.

```ui
{"type": "checklist", "title": "Helpdesk test", "items": [{"text": "Create ticket", "state": "done"}, {"text": "Cycle through statuses", "state": "active"}, {"text": "Check portal", "state": "open"}]}
```
A checklist for tasks with several steps. state: open, active, done or failed. Show it at the start and again with the new state when something changed, not after every single step.

Use building blocks sparingly: only where they really save a click, never as decoration.""")
