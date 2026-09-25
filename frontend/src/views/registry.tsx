import { lazy, type ComponentType } from 'react'
import type { Settings } from '@/lib/bootstrap'
import { ChatView } from './chat/ChatView'
import { SessionsSide } from './chat/SessionsSide'

// Alles außer dem Chat wird erst beim Öffnen geladen — der Start bleibt klein.
const CalendarMain = lazy(() =>
  import('./calendar/CalendarMain').then((m) => ({ default: m.CalendarMain })),
)
const CalendarSide = lazy(() =>
  import('./calendar/CalendarSide').then((m) => ({ default: m.CalendarSide })),
)
const McpMain = lazy(() => import('./mcp/McpMain').then((m) => ({ default: m.McpMain })))
const McpSide = lazy(() => import('./mcp/McpSide').then((m) => ({ default: m.McpSide })))
const SkillsMain = lazy(() =>
  import('./skills/SkillsMain').then((m) => ({ default: m.SkillsMain })),
)
const SkillsSide = lazy(() =>
  import('./skills/SkillsSide').then((m) => ({ default: m.SkillsSide })),
)
const MailMain = lazy(() => import('./mail/MailMain').then((m) => ({ default: m.MailMain })))
const MailSide = lazy(() => import('./mail/MailSide').then((m) => ({ default: m.MailSide })))
const SettingsMain = lazy(() =>
  import('./settings/SettingsMain').then((m) => ({ default: m.SettingsMain })),
)
const SettingsSide = lazy(() =>
  import('./settings/SettingsSide').then((m) => ({ default: m.SettingsSide })),
)

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
  { key: 'chat', icon: '💬', label: 'Chats', Side: SessionsSide, Main: ChatView },
  {
    key: 'skills',
    icon: '⚡',
    label: 'Skills',
    tile: 'skills',
    Side: SkillsSide,
    Main: SkillsMain,
  },
  {
    key: 'calendar',
    icon: '📅',
    label: 'Kalender',
    tile: 'kalender',
    Side: CalendarSide,
    Main: CalendarMain,
  },
  { key: 'mail', icon: '📧', label: 'E-Mails', tile: 'mail', Side: MailSide, Main: MailMain },
  { key: 'mcp', icon: '🔌', label: 'MCP', tile: 'mcp', Side: McpSide, Main: McpMain },
  { key: 'settings', icon: '⚙', label: 'Einstellungen', Side: SettingsSide, Main: SettingsMain },
]

export const visibleViews = (tiles: Settings['tiles']) =>
  VIEWS.filter((v) => !v.tile || tiles[v.tile] !== false)
