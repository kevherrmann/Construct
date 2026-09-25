import { tk } from '@/lib/i18n'
import type { Provider } from '@/api/providers'
import { baseName } from '@/lib/format'
import { useChat } from '@/stores/chat'
import { useDialogs } from '@/stores/dialogs'
import { useSettings } from '@/stores/settings'
import { CLAUDE_MODELS, MODES, extModels } from './models'

// App-eigene Slash-Befehle. Claudes eingebaute funktionieren im Headless-Modus
// nicht — das hier sind eigene.

export interface CommandContext {
  providers: Provider[]
  folders: string[]
  navigate: (to: string) => void
  /** Öffnet ein Auswahlmenü unten (ohne Argument aufgerufen). */
  openPicker: (p: 'model' | 'mode' | 'folder') => void
}

export function runCommand(raw: string, ctx: CommandContext) {
  const chat = useChat.getState()
  const parts = raw.slice(1).trim().split(/\s+/)
  const cmd = (parts[0] ?? '').toLowerCase()
  const arg = parts.slice(1).join(' ')
  const say = (key: string, params?: Record<string, string>, code?: string[]) =>
    chat.addSys({ type: 'text', note: { key, params }, code })

  if (cmd === '' || cmd === 'help') return chat.addSys({ type: 'help' })
  if (cmd === 'new') return chat.newSession()
  if (cmd === 'clear') return chat.clear()
  if (cmd === 'skills') return ctx.navigate('/skills')
  if (cmd === 'login') {
    const { boot } = useSettings.getState()
    return useDialogs.getState().open(boot.claude && boot.web_login ? 'login' : 'claude')
  }
  if (cmd === 'llm' || cmd === 'anbieter') return useDialogs.getState().open('providers')
  if (cmd === 'model') {
    if (!arg) return ctx.openPicker('model')
    const a = arg.toLowerCase()
    const ext = extModels(ctx.providers)
    const all = [...CLAUDE_MODELS, ...ext]
    const m =
      all.find((x) => (x.v || 'standard').toLowerCase() === a || x.l.toLowerCase() === a) ??
      all.find((x) => x.v.toLowerCase().endsWith(`:${a}`)) ??
      all.find((x) => x.l.toLowerCase().startsWith(a) || x.v.toLowerCase().includes(a))
    if (m) {
      chat.setModel(m.v)
      return m.prov
        ? say(tk('Modell → {m} ({d} · nur Chat)'), { m: m.l, d: m.d })
        : say(tk('Modell → {m}'), { m: m.l })
    }
    return say(
      ext.length
        ? tk('Unbekanntes Modell. Verfügbar:')
        : tk('Unbekanntes Modell. Externe Anbieter erst über /llm einrichten. Claude:'),
      undefined,
      [...CLAUDE_MODELS.map((x) => x.v || 'standard'), ...ext.slice(0, 12).map((x) => x.v)],
    )
  }
  if (cmd === 'mode') {
    if (!arg) return ctx.openPicker('mode')
    const a = arg.toLowerCase()
    const m = MODES.find((x) => x.v.toLowerCase() === a || x.l.toLowerCase().includes(a))
    if (m) {
      chat.setMode(m.v)
      return say(tk('Mode → {m}'), { m: m.l })
    }
    return say(
      tk('Unbekannter Mode. Verfügbar:'),
      undefined,
      MODES.map((x) => x.v),
    )
  }
  if (cmd === 'folder') {
    if (!arg) return ctx.openPicker('folder')
    const p = ctx.folders.find((x) => baseName(x).toLowerCase() === arg.toLowerCase())
    if (p) {
      chat.setFolder(p)
      return say(tk('Ordner → {f}'), { f: baseName(p) })
    }
    return say(tk('Ordner nicht gefunden: {f}'), { f: arg })
  }
  return say(tk('Unbekannter Befehl /{c} — /help zeigt alle.'), { c: cmd })
}
