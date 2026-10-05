import type { AuthStatus } from '@/api/system'
import { queryClient } from '@/lib/queryClient'
import { tk } from '@/lib/i18n'
import type { SessionTickets } from '@/api/tickets'
import type { Provider } from '@/api/providers'
import { apiGet, apiPost } from '@/lib/api'
import { baseName } from '@/lib/format'
import { useChat } from '@/stores/chat'
import { useDialogs } from '@/stores/dialogs'
import { useSettings } from '@/stores/settings'
import { useAuftraegeAnsicht } from '@/views/auftraege/store'
import { CLAUDE_MODELS, EFFORTS, MODES, extModels } from './models'

// App-eigene Slash-Befehle. Claudes eingebaute funktionieren im Headless-Modus
// nicht — das hier sind eigene.

export interface CommandContext {
  providers: Provider[]
  folders: string[]
  navigate: (to: string) => void
  /** Öffnet ein Auswahlmenü unten (ohne Argument aufgerufen). */
  openPicker: (p: 'model' | 'mode' | 'folder' | 'effort') => void
}

/** `/ticket` zeigt die Tickets der Session, `/ticket Titel` setzt einen Schnitt:
 *  ab der nächsten Nachricht gilt ein neues Ticket. Steht hinter der ersten Zeile
 *  noch Text, geht der gleich als Nachricht ab. Kostet keine Tokens. */
function ticketBefehl(raw: string) {
  const chat = useChat.getState()
  const say = (key: string, params?: Record<string, string>, code?: string[]) =>
    chat.addSys({ type: 'text', note: { key, params }, code })
  if (useSettings.getState().settings.tiles.tickets === false)
    return say(tk('Tickets sind abgeschaltet (⚙ Einstellungen → Kacheln).'))
  const c = chat.active()
  if (!c) return
  const [kopf = '', ...rest] = raw.replace(/^\/ticket\b[ \t]*/i, '').split('\n')
  const titel = kopf.trim()
  const text = rest.join('\n').trim()
  const sid = c.sessionId
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['tickets'] })

  if (!titel) {
    if (!sid) return say(tk('Noch keine Tickets in dieser Session.'))
    void apiGet<SessionTickets>(`/api/tickets/${encodeURIComponent(sid)}`).then((d) => {
      const zeilen = [...d.tickets]
        .reverse()
        .map(
          (t) =>
            `${t.nr === d.aktuell ? '▸' : t.status === 'erledigt' ? '✓' : '○'} #${t.nr} ${t.titel}`,
        )
      say(
        zeilen.length ? tk('Tickets dieser Session:') : tk('Noch keine Tickets in dieser Session.'),
        undefined,
        zeilen,
      )
    })
    return
  }
  const weiter = () => {
    if (text) void useChat.getState().send(text)
  }
  if (!sid) {
    chat.setTicketVorgabe(titel)
    say(tk('Neues Ticket: {t} — gilt ab der nächsten Nachricht.'), { t: titel })
    return weiter()
  }
  void apiPost(`/api/tickets/${encodeURIComponent(sid)}/schnitt`, { titel, cwd: c.cwd ?? '' })
    .then(() => {
      refresh()
      say(tk('Neues Ticket: {t} — gilt ab der nächsten Nachricht.'), { t: titel })
      weiter()
    })
    .catch(() => say(tk('Ticket konnte nicht angelegt werden.')))
}

/** `/firma Aufgabe` gibt die Aufgabe an die Firma (Team-Modus) — ohne dass der Assistent
 *  darüber entscheidet. Gehört die Session schon zu einem Ticket, wird es mit dem
 *  Auftrag verbunden: wird der fertig, gilt das Ticket als erledigt. `/firma` allein
 *  zeigt, was gerade bei der Firma liegt. */
function firmaBefehl(raw: string) {
  const chat = useChat.getState()
  const say = (key: string, params?: Record<string, string>, code?: string[]) =>
    chat.addSys({ type: 'text', note: { key, params }, code })
  if (!useSettings.getState().settings.team.aktiv)
    return say(tk('Der Team-Modus ist aus (⚙ Einstellungen → Team).'))
  const brief = raw.replace(/^\/firma\b[ \t]*/i, '').trim()
  if (!brief) {
    void apiGet<{ tickets: { titel: string; status: string }[] }>('/api/team/auftraege').then((d) =>
      say(
        d.tickets.length ? tk('Aufträge bei der Firma:') : tk('Noch keine Aufträge.'),
        undefined,
        d.tickets.map(
          (x) =>
            `${x.status === 'fertig' ? '✓' : x.status.startsWith('wartet') ? '⏸' : '⚙'} ${x.titel}`,
        ),
      ),
    )
    return
  }
  const c = chat.active()
  const sid = c?.sessionId
  void (async () => {
    let bruecke: { session: string; nr: number } | undefined
    if (sid) {
      const d = await apiGet<SessionTickets>(`/api/tickets/${encodeURIComponent(sid)}`).catch(
        () => null,
      )
      if (d?.aktuell) bruecke = { session: sid, nr: d.aktuell }
    }
    try {
      const j = await apiPost<{ ticket: { id: string; titel: string } }>('/api/team/auftraege', {
        brief,
        cwd: c?.cwd ?? '',
        bruecke,
      })
      void queryClient.invalidateQueries({ queryKey: ['team'] })
      void queryClient.invalidateQueries({ queryKey: ['tickets'] })
      say(tk('An die Firma gegeben: {t} — der Stand steht unter Aufträge.'), { t: j.ticket.titel })
      useAuftraegeAnsicht.getState().oeffne(j.ticket.id)
    } catch (e) {
      say(tk('Die Firma hat den Auftrag nicht angenommen: {e}'), { e: (e as Error).message })
    }
  })()
}

export function runCommand(raw: string, ctx: CommandContext) {
  const chat = useChat.getState()
  const parts = raw.slice(1).trim().split(/\s+/)
  const cmd = (parts[0] ?? '').toLowerCase()
  const arg = parts.slice(1).join(' ')
  const say = (key: string, params?: Record<string, string>, code?: string[]) =>
    chat.addSys({ type: 'text', note: { key, params }, code })

  if (cmd === '' || cmd === 'help') return chat.addSys({ type: 'help' })
  if (cmd === 'ticket') return ticketBefehl(raw)
  if (cmd === 'firma') return firmaBefehl(raw)
  if (cmd === 'new') return chat.newSession()
  if (cmd === 'clear') return chat.clear()
  if (cmd === 'skills') {
    // Abgeschaltete Kachel: auch per Befehl nicht erreichbar, wie früher.
    if (useSettings.getState().settings.tiles.skills === false) return
    return ctx.navigate('/skills')
  }
  if (cmd === 'login') {
    const { boot } = useSettings.getState()
    const auth = queryClient.getQueryData<AuthStatus>(['auth-status'])
    const cli = auth?.cli ?? boot.claude
    const web = auth?.can_web_login ?? boot.web_login
    return useDialogs.getState().open(cli && web ? 'login' : 'claude')
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
  if (cmd === 'effort' || cmd === 'aufwand') {
    if (!arg) return ctx.openPicker('effort')
    const a = arg.toLowerCase()
    const e = EFFORTS.find((x) => (x.v || 'standard') === a || x.l.toLowerCase() === a)
    if (e) {
      chat.setEffort(e.v)
      return say(tk('Aufwand → {e}'), { e: e.l })
    }
    return say(
      tk('Unbekannter Aufwand. Verfügbar:'),
      undefined,
      EFFORTS.map((x) => x.v || 'standard'),
    )
  }
  if (cmd === 'folder') {
    if (!arg) return ctx.openPicker('folder')
    // "fahrsignal" oder – bei gleichen Namen in Unterordnern – "kunden/fahrsignal"
    const want = arg.toLowerCase().replace(/^\/+|\/+$/g, '')
    const p = ctx.folders.find((x) => {
      const lx = x.toLowerCase()
      return baseName(lx) === want || lx.endsWith(`/${want}`)
    })
    if (p) {
      chat.setFolder(p)
      return say(tk('Ordner → {f}'), { f: baseName(p) })
    }
    return say(tk('Ordner nicht gefunden: {f}'), { f: arg })
  }
  return say(tk('Unbekannter Befehl /{c} — /help zeigt alle.'), { c: cmd })
}
