import type { Berechtigung, Effort, Modell } from '@/api/team'

// Auswahllisten der Personalakte — gespiegelt aus server/team/agents.py.

// Die Aliase laufen auf das jeweils neueste Modell (wie lib/chat/models.ts).
export const MODELLE: Record<Modell, string> = {
  fable: 'Fable 5.1',
  opus: 'Opus 5.5',
  sonnet: 'Sonnet 5.5',
  haiku: 'Haiku 4.5 · 200K',
}

export const EFFORTS: Effort[] = ['low', 'medium', 'high', 'xhigh', 'max']

/** Nur drei Modi (Messtabelle in agents.py): `plan` konnte nie etwas liefern,
 *  `default` und `dontAsk` verhielten sich wie `auto` — drei Namen für eine Sache. */
export const MODI: { v: Berechtigung; l: string }[] = [
  { v: 'acceptEdits', l: 'acceptEdits — darf Dateien ändern (Normalfall zum Bauen)' },
  { v: 'auto', l: 'auto — streng: nur was in den Werkzeugen steht (für Prüfer)' },
  {
    v: 'bypassPermissions',
    l: 'bypassPermissions — fragt nie, darf alles ⚠ nur im eigenen Ordner',
  },
]

/** Werkzeuge, die eine Akte vergeben darf (wie KNOWN_TOOLS in server/team/agents.py),
 *  mit kurzer Erklärung für den Tooltip. TodoWrite gibt es in der CLI nicht mehr. */
export const WERKZEUGE: { w: string; d: string }[] = [
  { w: 'Read', d: 'Dateien lesen' },
  { w: 'Write', d: 'Dateien anlegen und überschreiben' },
  { w: 'Edit', d: 'Dateien gezielt ändern' },
  { w: 'Bash', d: 'Befehle ausführen (bauen, testen, Screenshots)' },
  { w: 'Grep', d: 'in Dateien suchen' },
  { w: 'Glob', d: 'Dateien nach Muster finden' },
  { w: 'WebSearch', d: 'im Netz suchen' },
  { w: 'WebFetch', d: 'Webseiten abrufen' },
  { w: 'NotebookEdit', d: 'Jupyter-Notebooks ändern' },
  { w: 'Task', d: 'Unteragenten starten' },
  { w: 'Skill', d: 'Skills benutzen' },
  { w: 'TaskCreate', d: 'Aufgabenliste: Aufgabe anlegen' },
  { w: 'TaskUpdate', d: 'Aufgabenliste: Aufgabe abhaken oder ändern' },
  { w: 'TaskList', d: 'Aufgabenliste: alle zeigen' },
  { w: 'TaskGet', d: 'Aufgabenliste: eine Aufgabe lesen' },
]

/** Wie die Bremsen der Firma heißen, wenn sie einen Auftrag anhalten (guards.NAMEN). */
export const BREMSEN: Record<string, string> = {
  hin_und_her: 'Endlosschleife zwischen zwei',
  schritte: 'zu viele Schritte',
  tiefe: 'zu oft weitergereicht',
  pingpong: 'Ping-Pong erkannt',
  wiederholung: 'Wiederholung erkannt',
  kein_fortschritt: 'kein Fortschritt',
  akte: 'Personalakte blockiert die Arbeit',
  stille: 'Zug hängt',
  stiller_zug: 'Zug ohne Ergebnis',
  fehler: 'Zug mit Fehler beendet',
  neustart: 'Serverneustart',
  gestoppt: 'Zug gestoppt',
  zug_timeout: 'Zug abgelaufen',
  eskaliert: 'Rückfrage aus der Firma',
  unbekannt: 'Empfänger unbekannt',
}
