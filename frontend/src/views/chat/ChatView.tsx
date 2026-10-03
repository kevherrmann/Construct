import { useEffect, useLayoutEffect, useRef } from 'react'
import { useSearchParams } from 'react-router'
import { useSessions, type SessionInfo } from '@/api/chat'
import { ChatItemView } from '@/components/chat/Message'
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
  useEffect(() => {
    if (!wanted || !sessions.data) return
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
  }, [wanted, params, sessions.data, openSession, setParams])

  return (
    <div>
      {items.map((it) => (
        <ChatItemView key={it.id} item={it} busy={!!conv?.busy} />
      ))}
      <div ref={end} />
    </div>
  )
}
