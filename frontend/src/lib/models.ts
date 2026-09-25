// Claude-Modelle für Auswahllisten (🧠-Picker, Telegram). Leerer Wert =
// Konto-Standard von Claude Code. Längere IDs zuerst: Rückführungen laufen über
// den Präfix, und "claude-opus-5-5" fängt nun einmal mit "claude-opus-5" an.
export interface ClaudeModel {
  v: string
  /** Anzeigename; nur "Standard" wird übersetzt. */
  l: string
  /** Deutscher Quelltext der Beschreibung. */
  d: string
}

export const CLAUDE_MODELS: ClaudeModel[] = [
  { v: '', l: 'Standard', d: 'Konto-Standard von Claude Code' },
  {
    v: 'claude-opus-5-5',
    l: 'Opus 5.5',
    d: 'neuestes Opus — stark für Coding und komplexe Aufgaben',
  },
  {
    v: 'claude-fable-5-1',
    l: 'Fable 5.1',
    d: 'stärkstes Modell — für die härtesten und längsten Aufgaben',
  },
  { v: 'claude-opus-5', l: 'Opus 5', d: 'Vorgänger von Opus 5.5' },
  { v: 'claude-sonnet-5', l: 'Sonnet 5', d: 'schnell, schont das Limit' },
  { v: 'claude-haiku-4-5', l: 'Haiku 4.5', d: 'am schnellsten — kleine Aufgaben' },
]
