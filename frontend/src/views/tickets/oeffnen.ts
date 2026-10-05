import { useNavigate } from 'react-router'
import { useSessions, type SessionInfo } from '@/api/chat'
import { useChat } from '@/stores/chat'
import { useUi } from '@/stores/ui'
import { chatLink } from './format'

/** Eine Session (und darin eine Nachricht) aus der Ticket-Übersicht öffnen.
 *  In der Chat-Ansicht ist das ein Sprung per Adresse; im Construct-Raum gibt
 *  es keine Chat-Seite, dort wird die Session direkt geladen. */
export function useOeffnen(onDone?: () => void) {
  const navigate = useNavigate()
  const raum = useUi((st) => st.raum)
  const sessions = useSessions().data
  const openSession = useChat((st) => st.openSession)
  return (t: { session: string; project: string }, cwd: string, msg?: string) => {
    if (!raum) return navigate(chatLink(t, cwd, msg))
    const gelistet = sessions?.sessions.find((x) => x.id === t.session)
    const s: SessionInfo = gelistet
      ? { ...gelistet, cwd: cwd || gelistet.cwd }
      : {
          id: t.session,
          project: t.project,
          cwd,
          title: '',
          renamed: false,
          mtime: 0,
          archived: false,
          agent: '',
        }
    void openSession(s, sessions?.running[t.session])
    onDone?.()
  }
}
