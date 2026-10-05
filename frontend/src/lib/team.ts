import type { Berechtigung, Effort, Modell } from '@/api/team'

// Auswahllisten der Personalakte — gespiegelt aus server/team/agents.py.

export const MODELLE: Record<Modell, string> = {
  fable: 'Fable 5',
  opus: 'Opus 5',
  sonnet: 'Sonnet 5',
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

export const WERKZEUGE = [
  'Read',
  'Write',
  'Edit',
  'Bash',
  'Grep',
  'Glob',
  'WebSearch',
  'WebFetch',
  'NotebookEdit',
  'Task',
  'TodoWrite',
  'Skill',
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

export const fmtGroesse = (b: number) =>
  b < 1024
    ? `${b} B`
    : b < 1048576
      ? `${Math.round(b / 1024)} kB`
      : `${(b / 1048576).toFixed(1)} MB`
