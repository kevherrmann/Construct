import { useNavigate } from 'react-router'
import { useSessions, type SessionInfo } from '@/api/chat'
import { useChat } from '@/stores/chat'
import { useUi } from '@/stores/ui'
import { chatLink, transkriptOrdner } from '@/views/tickets/format'

/** Eine Session (und darin eine Nachricht) öffnen — von einer Karte des Ticket-Boards
 *  oder aus einer Meldung der Firma. In der Chat-Ansicht ist das ein Sprung per
 *  Adresse; im Construct-Raum gibt es keine Chat-Seite, dort wird die Session direkt
 *  geladen. `ordner` hilft nur, wenn die Session (noch) nicht in der Liste steht. */
export function useSessionOeffnen(onDone?: () => void) {
  const navigate = useNavigate()
  const raum = useUi((st) => st.raum)
  const sessions = useSessions().data
  const openSession = useChat((st) => st.openSession)
  return (session: string, ordner = '', msg?: string) => {
    const gelistet = sessions?.sessions.find((x) => x.id === session)
    const cwd = gelistet?.cwd || ordner
    const project = gelistet?.project || transkriptOrdner(ordner)
    if (!raum) return navigate(chatLink({ session, project }, cwd, msg))
    const s: SessionInfo = gelistet ?? {
      id: session,
      project,
      cwd,
      title: '',
      renamed: false,
      mtime: 0,
      archived: false,
      agent: '',
    }
    void openSession(s, sessions?.running[session])
    onDone?.()
  }
}
