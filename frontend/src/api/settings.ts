import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPost } from '@/lib/api'

// Alles, was die Einstellungsseite außer settings.json braucht
// (die liegt im Zustand-Store, siehe stores/settings.ts).

// ---------- Werkzeug-Maschinen (app.py → /api/engines) ----------
export interface Engines {
  claude: { installed: boolean; path: string | null; web_login: boolean; npm: boolean }
  hermes: { installed: boolean; path: string; version: string; home: string; posix: boolean }
}

export type Engine = 'claude' | 'hermes'

/** Installationslauf (hermes.install_state / app.claude_install_state). */
export interface InstallState {
  running: boolean
  done: boolean
  log: string[]
  error: string
  installed: boolean
  version?: string
}

export const useEngines = () =>
  useQuery({ queryKey: ['engines'], queryFn: () => apiGet<Engines>('/api/engines') })

export const startInstall = (which: Engine) =>
  apiPost<{ ok: boolean }>(`/api/engines/${which}/install`)
export const installState = (which: Engine) => apiGet<InstallState>(`/api/engines/${which}/install`)

// ---------- Aktualisierung (updates.state) ----------
export interface UpdateStep {
  state: 'idle' | 'run' | 'ok' | 'new' | 'error' | 'skip'
  from: string
  to: string
  msg: string
}

export interface UpdateState {
  running: boolean
  done: boolean
  started: number
  finished: number
  trigger: string
  changed: boolean
  log: string[]
  steps: Record<string, UpdateStep>
  /** Unix-Zeit der letzten Prüfung, 0 = nie. */
  last_check: number
}

export const updatesState = () => apiGet<UpdateState>('/api/updates')
export const runUpdates = () =>
  apiPost<{ ok?: boolean; error?: string; already?: boolean }>('/api/updates/run')

// ---------- Charakter (SOUL.md / USER.md) ----------
export type PersonaKey = 'soul' | 'user'
export type Persona = Record<PersonaKey, string>

export const usePersona = () =>
  useQuery({
    queryKey: ['persona'],
    queryFn: () => apiGet<Persona>('/api/persona'),
    staleTime: Infinity,
  })
export const savePersona = (patch: Partial<Persona>) =>
  apiPost<{ ok: boolean }>('/api/persona', patch)

// ---------- Telegram (telegram_bot.public_conf) ----------
export type TelegramState = 'off' | 'starting' | 'running' | 'conflict' | 'error'

export interface TelegramConf {
  enabled: boolean
  chat_id: number
  model: string
  mode: 'bypassPermissions' | 'plan'
  reminders: boolean
  reminder_hour: number
  reminder_lead: number
  notify: boolean
  has_token: boolean
  /** Token kommt aus TELEGRAM_TOKEN — dann hier nicht änderbar. */
  from_env: boolean
  status: {
    state: TelegramState
    error: string
    bot: string
    /** Wer dem Bot zuletzt geschrieben hat, solange keine Chat-ID gesetzt ist. */
    candidate: { id: number | string; name: string } | null
  }
}

export type TelegramPatch = Partial<
  Omit<TelegramConf, 'has_token' | 'from_env' | 'status' | 'chat_id'>
> & { chat_id?: string | number; token?: string }

// Solange die Seite offen ist, alle 3 s: so taucht die Chat-ID auf, sobald
// man dem Bot schreibt.
export const useTelegram = () =>
  useQuery({
    queryKey: ['telegram'],
    queryFn: () => apiGet<TelegramConf>('/api/telegram'),
    refetchInterval: 3000,
  })
export const saveTelegram = (patch: TelegramPatch) => apiPost<TelegramConf>('/api/telegram', patch)
export const testTelegram = () => apiPost<{ ok: boolean }>('/api/telegram/test')

// ---------- Vorlesen: Stimmen (tts.list_voices) ----------
export interface Voice {
  id: string
  name: string
  gender: string
  pitch: string
  accent: string
  type: string
  description: string
}

export const useTtsVoices = (lang: string) =>
  useQuery({
    queryKey: ['tts-voices', lang],
    queryFn: () => apiGet<{ voices: Voice[] }>(`/api/tts/voices?lang=${encodeURIComponent(lang)}`),
    staleTime: Infinity,
    retry: false,
  })

// ---------- Hochladen (attach.store) ----------
export interface Upload {
  path: string
  url: string
  name: string
  kind: 'image' | 'pdf'
}

export function uploadFile(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  // Leere headers: der Browser setzt den multipart-Rand selbst.
  return apiPost<Upload>('/api/upload', undefined, { body: fd, headers: {} })
}
