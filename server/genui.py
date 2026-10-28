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
Der Chat kann zwei Bausteine zeichnen. Schreib dafür einen Codeblock mit der Sprache `ui` und genau einem JSON-Objekt darin, ohne Kommentare:

```ui
{"type": "choices", "options": ["Erst testen", "Gleich committen"]}
```
Antwort-Buttons, wenn der Nutzer zwischen wenigen klaren Möglichkeiten wählen soll (höchstens 6, kurz). Ein Klick schickt den Text der Option als seine Antwort. Die Frage stellst du im Text davor; `"question"` nur, wenn sie dort nicht schon steht, sonst liest er sie doppelt. Nur am Ende deiner Antwort, und nur wenn du danach wirklich auf seine Wahl wartest.

```ui
{"type": "event", "title": "Zahnarzt", "date": "2026-11-03", "time": "09:30", "notes": ""}
```
Eine Terminkarte mit Knopf „Eintragen“, wenn du einen Termin vorschlägst, den der Nutzer noch nicht bestätigt hat. Datum als JJJJ-MM-TT, Uhrzeit HH:MM oder leer für ganztägig. Hat er den Termin schon bestätigt, trag ihn selbst ein statt eine Karte zu zeigen.

Setz Bausteine sparsam ein: nur wo sie wirklich einen Klick sparen, nie als Schmuck.""",
        """## Building blocks in the chat
The chat can draw two building blocks. Write a code block with the language `ui` containing exactly one JSON object, no comments:

```ui
{"type": "choices", "options": ["Test first", "Commit right away"]}
```
Answer buttons, when the user should pick between a few clear options (6 at most, short). A click sends the option's text as their reply. Ask the question in the text before it; add `"question"` only if it is not already there, otherwise they read it twice. Only at the end of your reply, and only when you really wait for their choice.

```ui
{"type": "event", "title": "Dentist", "date": "2026-11-03", "time": "09:30", "notes": ""}
```
An event card with an "Add to calendar" button, when you suggest an event the user has not confirmed yet. Date as YYYY-MM-DD, time HH:MM or empty for all day. If they already confirmed it, add it yourself instead of showing a card.

Use building blocks sparingly: only where they really save a click, never as decoration.""")
