import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPost } from '@/lib/api'
import { useSettings } from '@/stores/settings'

// Das Ticket-Board (server/tickets.py): Karten von Hand, aus Commits und aus
// Aufträgen der Firma, in fünf Spalten. Gepusht = Done, das prüft der Server.

export const SPALTEN = ['neu', 'arbeit', 'review', 'qa', 'done'] as const
export type Spalte = (typeof SPALTEN)[number]

/** Deutsche Quelltexte der Spaltennamen (übersetzt über i18n). */
export const SPALTEN_NAME: Record<Spalte, string> = {
  neu: 'Neu',
  arbeit: 'In Arbeit',
  review: 'In Review',
  qa: 'QA',
  done: 'Done',
}

export interface Commit {
  sha: string
  repo: string
  branch: string
  betreff: string
  ts: string
  /** Mitarbeiter der Firma, der committet hat; leer = der Assistent. */
  von: string
  gepusht: boolean
}

export interface Ticket {
  nr: number
  titel: string
  text: string
  spalte: Spalte
  /** Repo oder Arbeitsordner, zu dem die Karte gehört. */
  projekt: string
  von: string
  erstellt: string
  geaendert: string
  /** Chat-Session und Nachricht, aus der die Karte stammt: Sprung in den Verlauf. */
  session: string
  uuid: string
  /** Auftrag der Firma, der an dieser Karte arbeitet. */
  auftrag: string | null
  commits: Commit[]
}

export interface Board {
  spalten: Spalte[]
  tickets: Ticket[]
  projekte: { pfad: string; name: string }[]
}

export const useTicketsAn = () => useSettings((st) => st.settings.tiles.tickets !== false)

export const useBoard = (aktiv = true) =>
  useQuery({
    queryKey: ['tickets', 'board'],
    queryFn: () => apiGet<Board>('/api/tickets'),
    enabled: aktiv,
    refetchOnMount: 'always',
    // Commits und die Firma schieben Karten, ohne dass das Board es mitbekommt.
    refetchInterval: 10_000,
  })

export function useTicketActions() {
  const qc = useQueryClient()
  const fertig = () => void qc.invalidateQueries({ queryKey: ['tickets'] })
  // Ein Fehlschlag soll nicht stumm bleiben: dann sähe es aus, als hätte der Klick nichts getan.
  const useAktion = <V, R>(fn: (v: V) => Promise<R>) =>
    useMutation({ mutationFn: fn, onSuccess: fertig, onError: (e) => alert(e.message) })
  return {
    anlegen: useAktion((v: { titel: string; text?: string; projekt?: string; spalte?: Spalte }) =>
      apiPost<Ticket>('/api/tickets', v),
    ),
    aendern: useAktion(
      (v: { nr: number; titel?: string; text?: string; spalte?: Spalte; projekt?: string }) => {
        const { nr, ...rest } = v
        return apiPost<Ticket>(`/api/tickets/${nr}`, rest)
      },
    ),
    loeschen: useAktion((nr: number) => apiDelete<{ ok: boolean }>(`/api/tickets/${nr}`)),
  }
}

/** Name des Projekts aus dem Pfad. */
export const projektName = (pfad: string) => pfad.split(/[\\/]/).filter(Boolean).pop() ?? ''
