import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPost } from '@/lib/api'
import { useSettings } from '@/stores/settings'

// Tickets: Abschnitte einer Session (server/tickets.py). Ein Ticket sammelt die
// Nachrichten einer Aufgabe, auch mit Lücken dazwischen.

export type TicketStatus = 'offen' | 'erledigt'
export type TicketVon = 'kevin' | 'assistent' | 'auto'

export interface TicketMsg {
  /** uuid der Nachricht im Transkript. */
  id: string
  ts: string
  text: string
  von: TicketVon
}

export interface Ticket {
  nr: number
  titel: string
  status: TicketStatus
  von: TicketVon
  erstellt: string
  erledigt_am: string | null
  /** Team-Modus: der Auftrag der Firma, der aus diesem Ticket entstand. */
  auftrag: string | null
  nachrichten: TicketMsg[]
}

export interface SessionTickets {
  session: string
  cwd: string
  project: string
  /** Wohin die nächste Nachricht geht, wenn niemand etwas anderes sagt. */
  aktuell: number | null
  /** Der Nutzer hat gewählt: der Assistent ordnet die nächste Nachricht nicht um. */
  gesperrt: boolean
  tickets: Ticket[]
}

/** Ein Ticket in der Übersicht: dazu, in welcher Session und welcher Teil seiner Nachrichten
 *  an diesem Tag lag. */
export interface UebersichtTicket extends Omit<Ticket, 'nachrichten'> {
  session: string
  project: string
  session_titel: string
  aktuell: boolean
  nachrichten: TicketMsg[]
  gesamt: number
}

export interface UebersichtProjekt {
  cwd: string
  name: string
  offen: number
  erledigt: number
  tickets: UebersichtTicket[]
}

export interface Uebersicht {
  tage: { tag: string; projekte: UebersichtProjekt[] }[]
}

/** Läuft die Ticket-Zuordnung? Ein Schalter für alles: Kachel, Chip, ✂. */
export const useTicketsAn = () => useSettings((st) => st.settings.tiles.tickets !== false)

export const useSessionTickets = (sid: string | null | undefined) => {
  const an = useTicketsAn()
  return useQuery({
    queryKey: ['tickets', 'session', sid],
    queryFn: () => apiGet<SessionTickets>(`/api/tickets/${encodeURIComponent(sid!)}`),
    enabled: an && !!sid,
    refetchOnMount: 'always',
  })
}

export const useTicketUebersicht = () =>
  useQuery({
    queryKey: ['tickets', 'uebersicht'],
    queryFn: () => apiGet<Uebersicht>('/api/tickets'),
    refetchOnMount: 'always',
    // Der Assistent und die Nachrichten ändern laufend etwas.
    refetchInterval: 10_000,
  })

const url = (sid: string, rest = '') => `/api/tickets/${encodeURIComponent(sid)}${rest}`

/** Alle schreibenden Aufrufe liefern die ganze Session zurück und laden die Ansichten neu. */
export function useTicketActions(sid: string) {
  const qc = useQueryClient()
  const fertig = (d: SessionTickets) => {
    qc.setQueryData(['tickets', 'session', sid], d)
    void qc.invalidateQueries({ queryKey: ['tickets'] })
  }
  const useAktion = <V>(fn: (v: V) => Promise<SessionTickets>) =>
    useMutation({ mutationFn: fn, onSuccess: fertig })
  return {
    schnitt: useAktion((v: { titel: string; cwd?: string }) =>
      apiPost<SessionTickets>(url(sid, '/schnitt'), v),
    ),
    waehlen: useAktion((nr: number) => apiPost<SessionTickets>(url(sid, '/waehlen'), { nr })),
    aendern: useAktion((v: { nr: number; titel?: string; status?: TicketStatus }) =>
      apiPost<SessionTickets>(url(sid, `/${v.nr}`), { titel: v.titel, status: v.status }),
    ),
    loeschen: useAktion((nr: number) => apiDelete<SessionTickets>(url(sid, `/${nr}`))),
    zusammenfuehren: useAktion((v: { nr: number; in: number }) =>
      apiPost<SessionTickets>(url(sid, `/${v.nr}/zusammenfuehren`), { in: v.in }),
    ),
    umhaengen: useAktion((v: { uuids: string[]; nr: number }) =>
      apiPost<SessionTickets>(url(sid, '/umhaengen'), v),
    ),
    abHier: useAktion((v: { uuid: string; titel: string }) =>
      apiPost<SessionTickets>(url(sid, '/ab-hier'), v),
    ),
  }
}
