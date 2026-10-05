import { Fragment, useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router'
import { useSessions, type SessionInfo } from '@/api/chat'
import { useSessionTickets } from '@/api/tickets'
import { useTranslation } from 'react-i18next'
import { useAgentGespraech } from '@/api/team'
import { AgentKontext } from '@/components/chat/AgentKontext'
import { ChatItemView } from '@/components/chat/Message'
import { TicketTrenner } from '@/components/chat/TicketCut'
import { useChat } from '@/stores/chat'

// Hauptbereich: Verlauf der aktiven Unterhaltung plus der laufende Lauf.
export function ChatView() {
  const conv = useChat((st) => st.active())
  const pollTail = useChat((st) => st.pollTail)
  const openSession = useChat((st) => st.openSession)
  const sessions = useSessions()
  const [params, setParams] = useSearchParams()
  const end = useRef<HTMLDivElement>(null)
  const items = conv ? [...conv.history, ...(conv.run?.items ?? [])] : []

  // Wo ein Ticket beginnt, zieht der Verlauf eine Linie. Erst ab zwei Tickets:
  // eine Session mit einer einzigen Aufgabe braucht keine Gliederung.
  const tickets = useSessionTickets(conv?.sessionId).data
  const tickOf = useMemo(() => {
    const m = new Map<string, { nr: number; titel: string; erledigt: boolean }>()
    if (!tickets || tickets.tickets.length < 2) return m
    for (const t of tickets.tickets)
      for (const n of t.nachrichten)
        m.set(n.id, { nr: t.nr, titel: t.titel, erledigt: t.status === 'erledigt' })
    return m
  }, [tickets])
  let letztes = -1

  // /chat?…&msg=<uuid> (aus der Ticket-Übersicht): zu dieser Nachricht springen.
  const anker = useRef<string | null>(null)

  // Neues ins Bild holen — aber nur, wenn wirklich etwas dazukam (neue
  // Blase, wachsender Text, andere Unterhaltung). Jedes andere Neuzeichnen
  // würde sonst beim Hochscrollen wieder nach unten reißen.
  const last = items[items.length - 1]
  const lastBlock = last?.kind === 'bot' ? last.blocks[last.blocks.length - 1] : undefined
  const growth =
    last?.kind === 'bot'
      ? `${last.blocks.length}:${lastBlock?.t === 'text' ? lastBlock.text.length : 0}:${last.thinking}`
      : ''
  const signature = `${conv?.key}:${items.length}:${growth}`
  useLayoutEffect(() => {
    const scroller = end.current?.closest('[data-scroll]')
    if (scroller) scroller.scrollTop = scroller.scrollHeight
  }, [signature])

  // Bilder in Antworten laden erst nach dem Hinscrollen und schieben das Ende
  // dann wieder aus dem Bild. Wer unten war, bleibt unten. "Unten" richtet sich
  // nach dem, was der Nutzer tut: die Ansicht scrollt weich, und während der
  // Animation sähe jede Messung so aus, als stünde man mittendrin.
  useEffect(() => {
    const scroller = end.current?.closest('[data-scroll]')
    if (!scroller) return
    let unten = true
    const rest = () => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight
    const onScroll = () => {
      if (rest() < 120) unten = true
    }
    const hoch = () => {
      unten = false
    }
    const onWheel = (e: WheelEvent) => {
      if (e.deltaY < 0) hoch()
    }
    const onKey = (e: KeyboardEvent) => {
      if (['PageUp', 'ArrowUp', 'Home'].includes(e.key)) hoch()
    }
    // Auch ein Sprung zu einer Nachricht (Ticket-Übersicht) heißt: nicht wieder nach unten ziehen.
    scroller.addEventListener('construct:hoch', hoch)
    const onLoad = (e: Event) => {
      if (unten && (e.target as HTMLElement).tagName === 'IMG' && rest() > 0)
        scroller.scrollTop = scroller.scrollHeight
    }
    scroller.addEventListener('scroll', onScroll, { passive: true })
    scroller.addEventListener('wheel', onWheel as EventListener, { passive: true })
    scroller.addEventListener('touchmove', hoch, { passive: true })
    scroller.addEventListener('keydown', onKey as EventListener)
    scroller.addEventListener('load', onLoad, true)
    return () => {
      scroller.removeEventListener('scroll', onScroll)
      scroller.removeEventListener('wheel', onWheel as EventListener)
      scroller.removeEventListener('touchmove', hoch)
      scroller.removeEventListener('keydown', onKey as EventListener)
      scroller.removeEventListener('load', onLoad, true)
      scroller.removeEventListener('construct:hoch', hoch)
    }
  }, [])

  useEffect(() => {
    const id = setInterval(() => void pollTail(), 3000)
    const vis = () => {
      if (!document.hidden) void pollTail()
    }
    document.addEventListener('visibilitychange', vis)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', vis)
    }
  }, [pollTail])

  // /chat?session=<id>&project=…&cwd=… öffnet eine Session direkt (Tagebuch
  // im Kalender). Steht sie (noch) nicht in der Liste — gerade im Terminal
  // begonnen oder unter /tmp, das die Liste ausblendet —, reichen Projekt und
  // Ordner aus dem Link, wie früher. Der Ordner des Tages gewinnt: dort wurde
  // an dem Tag gearbeitet.
  const wanted = params.get('session')
  const msg = params.get('msg')
  useEffect(() => {
    if (!wanted || !sessions.data) return
    if (msg) anker.current = msg
    const listed = sessions.data.sessions.find((x) => x.id === wanted)
    const project = params.get('project') ?? listed?.project
    const cwd = params.get('cwd') || listed?.cwd || ''
    if (project) {
      const s: SessionInfo = listed
        ? { ...listed, cwd }
        : {
            id: wanted,
            project,
            cwd,
            title: '',
            renamed: false,
            mtime: 0,
            archived: false,
            agent: '',
          }
      void openSession(s, sessions.data.running[wanted])
    }
    setParams({}, { replace: true })
  }, [wanted, msg, params, sessions.data, openSession, setParams])

  useEffect(() => {
    const ziel = anker.current
    if (!ziel || !conv) return
    const el = [
      ...(end.current?.parentElement?.querySelectorAll<HTMLElement>('[data-uuid]') ?? []),
    ].find((x) => x.dataset.uuid === ziel)
    if (!el) return
    end.current?.closest('[data-scroll]')?.dispatchEvent(new Event('construct:hoch'))
    el.scrollIntoView({ block: 'center' })
    el.dataset.flash = '1'
    setTimeout(() => delete el.dataset.flash, 2000)
    anker.current = null
  }, [conv, items.length, wanted, msg])

  return (
    <AgentKontext.Provider value={conv?.agent ?? null}>
      {conv?.agent && <AgentKopf slug={conv.agent.slug} />}
      <div>
        {items.map((it) => {
          const tk = it.kind === 'user' && it.uuid ? tickOf.get(it.uuid) : undefined
          const trenner = tk && tk.nr !== letztes
          if (tk) letztes = tk.nr
          return (
            <Fragment key={it.id}>
              {trenner && <TicketTrenner nr={tk.nr} titel={tk.titel} erledigt={tk.erledigt} />}
              <ChatItemView item={it} busy={!!conv?.busy} />
            </Fragment>
          )
        })}
        <div ref={end} />
      </div>
    </AgentKontext.Provider>
  )
}

/** Kopf über einem Gespräch mit einem Mitarbeiter: wer, womit, wie voll das Gedächtnis ist.
 *  Bei 100 % fasst die Person das Gespräch selbst zusammen, hebt das Bleibende ins
 *  Gedächtnis und fängt frisch an. */
function AgentKopf({ slug }: { slug: string }) {
  const { t } = useTranslation()
  const { data } = useAgentGespraech(slug)
  if (!data) return null
  const a = data.agent
  const u = data.umfang
  const voll = Math.max(
    Math.round((u.bytes / u.max_bytes) * 100),
    Math.round((u.msgs / u.max_msgs) * 100),
  )
  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        alignItems: 'baseline',
        flexWrap: 'wrap',
        padding: '4px 4px 12px',
        borderBottom: `1px solid rgba(${a.color}, 0.35)`,
        marginBottom: 12,
        fontSize: 12,
        color: 'var(--green-dim)',
      }}
    >
      <b style={{ color: `rgb(${a.color})`, letterSpacing: 2, fontWeight: 'normal', fontSize: 14 }}>
        💬 {a.name.toUpperCase()}
      </b>
      <span>{a.title}</span>
      <span style={{ opacity: 0.6 }}>
        {a.model} / {a.effort}
      </span>
      {voll >= 50 && (
        <span
          style={{ opacity: 0.55 }}
          title={t('Ab 100 % fasst {n} das Gespräch zusammen und merkt sich das Wesentliche', {
            n: a.name,
          })}
        >
          · {t('Gedächtnis')} {voll} %
        </span>
      )}
    </div>
  )
}
