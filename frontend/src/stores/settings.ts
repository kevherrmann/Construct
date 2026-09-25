import { create } from 'zustand'
import { apiPost } from '@/lib/api'
import { readBootstrap, type Bootstrap, type Settings } from '@/lib/bootstrap'
import { applyTheme } from '@/lib/themes'

/** Teil-Update wie beim Server (config.apply_patch): verschachtelte Objekte teilweise. */
export type SettingsPatch = {
  [K in keyof Settings]?: Settings[K] extends Record<string, unknown>
    ? {
        [P in keyof Settings[K]]?: Settings[K][P] extends Record<string, unknown>
          ? Partial<Settings[K][P]>
          : Settings[K][P]
      }
    : Settings[K]
}

export type SaveState = 'idle' | 'saving' | 'saved' | 'error'

interface SettingsStore {
  boot: Bootstrap
  settings: Settings
  saveState: SaveState
  /** Sofort lokal übernehmen, dann speichern; die Antwort des Servers ist maßgeblich. */
  save: (patch: SettingsPatch) => Promise<void>
}

function merge(cur: Settings, patch: SettingsPatch): Settings {
  const out: Record<string, unknown> = { ...cur }
  for (const [k, v] of Object.entries(patch)) {
    const c = (cur as unknown as Record<string, unknown>)[k]
    if (v && typeof v === 'object' && c && typeof c === 'object') {
      const nested: Record<string, unknown> = { ...(c as Record<string, unknown>) }
      for (const [k2, v2] of Object.entries(v)) {
        const c2 = nested[k2]
        nested[k2] =
          v2 && typeof v2 === 'object' && c2 && typeof c2 === 'object' ? { ...c2, ...v2 } : v2
      }
      out[k] = nested
    } else out[k] = v
  }
  return out as unknown as Settings
}

const boot = readBootstrap()

export const useSettings = create<SettingsStore>((set, get) => ({
  boot,
  settings: boot.settings,
  saveState: 'idle',
  async save(patch) {
    const next = merge(get().settings, patch)
    set({ settings: next, saveState: 'saving' })
    if (patch.theme) applyTheme(next.theme)
    try {
      const fresh = await apiPost<Settings>('/api/settings', patch)
      set({ settings: fresh, saveState: 'saved' })
    } catch {
      set({ saveState: 'error' })
    }
  },
}))

export const __test = { merge }
