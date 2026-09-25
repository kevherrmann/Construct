// Was der Server beim Ausliefern der Seite mitgibt (app.py → index()).
// Spiegelt config.DEFAULT_SETTINGS — Felder hier ergänzen, wenn dort welche dazukommen.

export type Lang = 'de' | 'en'
export type ThemeName =
  'matrix' | 'bernstein' | 'eis' | 'space' | 'asche' | 'blut' | 'papier' | 'nebel' | 'plasma'

export interface Settings {
  theme: ThemeName
  lang: Lang
  names: { user: string; assistant: string }
  avatars: { user: string; assistant: string }
  hermes: { home: string }
  tiles: { skills: boolean; kalender: boolean; mail: boolean; mcp: boolean }
  background: { mode: 'matrix' | 'plain' | 'image'; image: string; dim: number }
  updates: { auto: boolean; interval_h: number; construct: boolean }
  tts: {
    auto: boolean
    model: string
    voice: Record<Lang, string>
    style: Record<Lang, string>
  }
}

export interface Bootstrap {
  user: string
  assistant: string
  claude: boolean
  web_login: boolean
  lang: Lang
  workspace: string
  settings: Settings
}

declare global {
  interface Window {
    CONSTRUCT?: Partial<Bootstrap>
  }
}

export const DEFAULT_SETTINGS: Settings = {
  theme: 'matrix',
  lang: 'en',
  names: { user: '', assistant: 'Cody' },
  avatars: { user: '', assistant: '' },
  hermes: { home: '' },
  tiles: { skills: false, kalender: true, mail: false, mcp: false },
  background: { mode: 'matrix', image: '', dim: 60 },
  updates: { auto: true, interval_h: 6, construct: true },
  tts: {
    auto: false,
    model: 'gemini-3.8-flash-lite-tts',
    voice: { de: 'de-de-podcaster-3', en: 'en-us-podcaster-6' },
    style: { de: '', en: '' },
  },
}

/** Liest window.CONSTRUCT und füllt Lücken mit Vorgaben (z. B. im Vite-Dev-Server). */
export function readBootstrap(src: Partial<Bootstrap> | undefined = window.CONSTRUCT): Bootstrap {
  const s = src ?? {}
  const settings: Settings = { ...DEFAULT_SETTINGS, ...(s.settings ?? {}) }
  const lang: Lang = s.lang === 'de' || settings.lang === 'de' ? 'de' : 'en'
  return {
    user: s.user ?? settings.names.user,
    assistant: s.assistant || settings.names.assistant || 'Cody',
    claude: s.claude ?? false,
    web_login: s.web_login ?? false,
    lang,
    workspace: s.workspace ?? '',
    settings: { ...settings, lang },
  }
}
