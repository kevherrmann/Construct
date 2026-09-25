import { useEffect, useLayoutEffect, useRef } from 'react'
import { useSearchParams } from 'react-router'
import { useSessions } from '@/api/chat'
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

  // Neues immer ins Bild holen — wie in der alten Oberfläche.
  useLayoutEffect(() => {
    const scroller = end.current?.closest('[data-scroll]')
    if (scroller) scroller.scrollTop = scroller.scrollHeight
  })

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

  // /chat?session=<id> öffnet eine Session direkt (Links aus dem Kalender).
  const wanted = params.get('session')
  useEffect(() => {
    if (!wanted || !sessions.data) return
    const s = sessions.data.sessions.find((x) => x.id === wanted)
    if (s) void openSession(s, sessions.data.running[s.id])
    setParams({}, { replace: true })
  }, [wanted, sessions.data, openSession, setParams])

  return (
    <div>
      {items.map((it) => (
        <ChatItemView key={it.id} item={it} busy={!!conv?.busy} />
      ))}
      <div ref={end} />
    </div>
  )
}
