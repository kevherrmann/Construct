import { Fragment, useEffect, useLayoutEffect, useRef } from 'react'
import { useSearchParams } from 'react-router'
import { useSessions, type SessionInfo } from '@/api/chat'
import { ChatItemView } from '@/components/chat/Message'
import { useFirmaImChat } from '@/components/firma/FirmaImChat'
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

  // Team-Modus: was die Firma in dieser Session schreibt, steht zwischen den eigenen
  // Nachrichten, nach Zeit einsortiert — ein Gruppenchat statt einer eigenen Ansicht.
  const firma = useFirmaImChat(conv?.sessionId)
  let fi = 0

  // /chat?…&msg=<uuid> (von einer Karte des Ticket-Boards): zu dieser Nachricht springen.
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
  const signature = `${conv?.key}:${items.length}:${growth}:${firma.zeilen.length}`
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
    // Auch ein Sprung zu einer Nachricht (Ticket-Board) heißt: nicht wieder nach unten ziehen.
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
    <div>
      {items.map((it) => {
        // Was die Firma vor dieser Nachricht geschrieben hat, kommt davor.
        const ts = 'ts' in it ? it.ts : undefined
        const vorher = []
        if (ts)
          while (fi < firma.zeilen.length && firma.zeilen[fi]!.ts < ts)
            vorher.push(firma.zeilen[fi++]!)
        return (
          <Fragment key={it.id}>
            {vorher.map((z) => (
              <Fragment key={z.key}>{z.node}</Fragment>
            ))}
            <ChatItemView item={it} busy={!!conv?.busy} />
          </Fragment>
        )
      })}
      {firma.zeilen.slice(fi).map((z) => (
        <Fragment key={z.key}>{z.node}</Fragment>
      ))}
      {firma.schluss}
      <div ref={end} />
    </div>
  )
}
