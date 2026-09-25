import type { ComponentType } from 'react'
import type { Settings } from '@/lib/bootstrap'
import { Placeholder } from './Placeholder'
import { SettingsMain } from './settings/SettingsMain'
import { SettingsSide } from './settings/SettingsSide'

export type ViewKey = 'chat' | 'skills' | 'calendar' | 'mail' | 'mcp' | 'settings'

export interface ViewDef {
  key: ViewKey
  icon: string
  /** Deutscher Quelltext, übersetzt über i18n. */
  label: string
  /** Abschaltbar unter ⚙ → Kacheln; fehlt = immer da. */
  tile?: keyof Settings['tiles']
  /** Inhalt der Seitenleiste unter dem Menü. */
  Side: ComponentType
  /** Hauptbereich rechts. */
  Main: ComponentType
}

// Reihenfolge = Reihenfolge im Menü.
export const VIEWS: ViewDef[] = [
  { key: 'chat', icon: '💬', label: 'Chats', Side: Placeholder, Main: Placeholder },
  {
    key: 'skills',
    icon: '⚡',
    label: 'Skills',
    tile: 'skills',
    Side: Placeholder,
    Main: Placeholder,
  },
  {
    key: 'calendar',
    icon: '📅',
    label: 'Kalender',
    tile: 'kalender',
    Side: Placeholder,
    Main: Placeholder,
  },
  { key: 'mail', icon: '📧', label: 'E-Mails', tile: 'mail', Side: Placeholder, Main: Placeholder },
  { key: 'mcp', icon: '🔌', label: 'MCP', tile: 'mcp', Side: Placeholder, Main: Placeholder },
  {
    key: 'settings',
    icon: '⚙',
    label: 'Einstellungen',
    Side: SettingsSide,
    Main: SettingsMain,
  },
]

export const visibleViews = (tiles: Settings['tiles']) =>
  VIEWS.filter((v) => !v.tile || tiles[v.tile] !== false)
