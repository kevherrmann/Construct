// Datenmodell des Chats. Die alte Oberfläche baute das DOM direkt aus den
// Stream-Events; hier wird daraus zuerst ein Zustand (ChatItem[]), den React
// zeichnet. Das macht Reconnect, Session-Wechsel und Tests einfach.

/** Ein Ereignis aus /api/stream/{run_id} (SSE, "data: {...}"). */
export type StreamEvent =
  | { type: 'session'; session_id: string }
  | { type: 'text'; text: string }
  | { type: 'user_inject'; text?: string; urls?: string[] }
  /** Ein Commit des Laufs ist als Karte aufs Ticket-Board gekommen. */
  | { type: 'tickets'; nr: number }
  /** Die Aufgabe ist an die Firma gegangen ([[firma: …]] am Ende der Antwort). */
  | { type: 'firma'; auftrag: string }
  | { type: 'thinking_marker' }
  /** `parent`: der Schritt gehört dem Helfer mit dieser id, nicht dem Assistenten. */
  | { type: 'tool'; id?: string; name: string; input?: unknown; parent?: string }
  | { type: 'tool_result'; id?: string; content?: string; is_error?: boolean; parent?: string }
  /** Ein Helfer (Agent/Task): Start, Fortschritt, Ende. Felder nur, wo der Stand sie kennt. */
  | {
      type: 'helfer'
      id: string
      stand: HelferStand
      beschreibung?: string
      typ?: string
      hintergrund?: boolean
      detail?: string
      werkzeug?: string
    }
  | { type: 'stats'; duration_ms?: number; out?: number; ctx?: number; model?: string }
  | { type: 'nachlauf'; tasks?: string[] }
  | { type: 'neuer_zug' }
  | { type: 'nachlauf_ende' }
  | { type: 'done'; session_id?: string }
  | { type: 'error'; message: string }
  /** Der Lauf ist zu Ende (letztes Ereignis jedes Streams). */
  | { type: 'closed' }

export type HelferStand = 'start' | 'laeuft' | 'fertig' | 'fehler'

/** Ein Helfer, den der Assistent gestartet hat (Werkzeug Agent/Task). */
export interface Helfer {
  /** tool_use_id des Agent-Aufrufs. */
  id: string
  /** Sprechblase (BotItem.id), in der er gestartet wurde. */
  antwort: string
  /** Was er tun soll („Datei eins.txt lesen“). */
  beschreibung: string
  /** subagent_type, etwa „Explore“ oder „general-purpose“. */
  typ: string
  stand: HelferStand
  /** Letztes Werkzeug des Helfers ('' = noch keins). */
  werkzeug: string
  /** Was er gerade tut, von claude formuliert („Reading eins.txt“). */
  detail: string
  /** Läuft im Hintergrund weiter, auch wenn der Zug fertig ist. */
  hintergrund: boolean
}

/** Hinweiszeile mit deutschem Quelltext, übersetzt beim Zeichnen. */
export interface NoteText {
  key: string
  params?: Record<string, string | number>
}

export type Block =
  | { t: 'text'; text: string; streaming: boolean }
  | { t: 'thinkmark' }
  | {
      t: 'tool'
      id?: string
      name: string
      input: unknown
      result?: { content: string; isError: boolean }
      /** Schritt eines Helfers (id seines Agent-Aufrufs); fehlt beim Assistenten selbst. */
      parent?: string
    }
  | { t: 'skill'; kind: 'used' | 'saved'; label: string }
  | { t: 'stats'; durationMs?: number; out?: number; ctx?: number; model?: string }
  | { t: 'files'; paths: string[] }
  | { t: 'note'; note: NoteText }
  | { t: 'error'; message: string }

export interface UserItem {
  kind: 'user'
  id: string
  text: string
  urls: string[]
  /** Nur eigene, direkt gesendete Nachrichten lassen sich bearbeiten. */
  editable: boolean
  /** Sendezeit (ms seit 1970); fehlt, wenn der Verlauf keine kennt. */
  ts?: number
  /** uuid der Nachricht im Transkript — dorthin springt eine Karte des Ticket-Boards. */
  uuid?: string
}

export interface BotItem {
  kind: 'bot'
  id: string
  blocks: Block[]
  /** "Denke nach …" mit pulsierenden Punkten, bis die erste Ausgabe kommt. */
  thinking: boolean
  /** Verlauf aus dem Transkript: fertiges Markdown statt Blöcken. */
  markdown?: string
  /** Beginn der Antwort (ms seit 1970). */
  ts?: number
}

/** Zeile ohne Sprechblase (Hinweise wie "Neue Session …", "Gestoppt."). */
export interface NoteItem {
  kind: 'note'
  id: string
  note: NoteText
  center?: boolean
}

/** Antwort eines App-Befehls (/help, /model …) in einer Hilfe-Box. */
export interface SysItem {
  kind: 'sys'
  id: string
  sys: SysBody
}

export type SysBody = { type: 'help' } | { type: 'text'; note: NoteText; code?: string[] }

export type ChatItem = UserItem | BotItem | NoteItem | SysItem

export interface TranscriptMessage {
  role: 'user' | 'assistant'
  text: string
  uuid?: string
  /** ISO-Zeit (Claude-Transkript) oder Unix-Sekunden (Hermes). */
  ts?: string | number
}
