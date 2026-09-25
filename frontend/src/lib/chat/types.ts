// Datenmodell des Chats. Die alte Oberfläche baute das DOM direkt aus den
// Stream-Events; hier wird daraus zuerst ein Zustand (ChatItem[]), den React
// zeichnet. Das macht Reconnect, Session-Wechsel und Tests einfach.

/** Ein Ereignis aus /api/stream/{run_id} (SSE, "data: {...}"). */
export type StreamEvent =
  | { type: 'session'; session_id: string }
  | { type: 'text'; text: string }
  | { type: 'user_inject'; text?: string; urls?: string[] }
  | { type: 'thinking_marker' }
  | { type: 'tool'; id?: string; name: string; input?: unknown }
  | { type: 'tool_result'; id?: string; content?: string; is_error?: boolean }
  | { type: 'stats'; duration_ms?: number; out?: number; ctx?: number; model?: string }
  | { type: 'nachlauf'; tasks?: string[] }
  | { type: 'neuer_zug' }
  | { type: 'nachlauf_ende' }
  | { type: 'done'; session_id?: string }
  | { type: 'error'; message: string }

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
}

export interface BotItem {
  kind: 'bot'
  id: string
  blocks: Block[]
  /** "Denke nach …" mit pulsierenden Punkten, bis die erste Ausgabe kommt. */
  thinking: boolean
  /** Verlauf aus dem Transkript: fertiges Markdown statt Blöcken. */
  markdown?: string
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
}
