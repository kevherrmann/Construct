import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiDelete } from '@/lib/api'

/** Ein Termin aus events.json (cal.py → add_event). */
export interface CalEvent {
  id: string
  /** YYYY-MM-DD; bei jährlichen zählt nur Monat-Tag. */
  date: string
  /** HH:MM oder leer = ganztägig. */
  time: string
  title: string
  notes: string
  /** "" = einmalig, "yearly" = jährlich (z. B. Geburtstag). */
  repeat: '' | 'yearly'
  /** Geplante Assistenten-Aufgabe: läuft zur Termin-Zeit, Ergebnis per Telegram. */
  prompt: string
  created: string
}

export interface NewEvent {
  date: string
  time: string
  title: string
  prompt: string
  repeat: '' | 'yearly'
}

/** Eine Session, in der an einem Tag in einem Ordner gearbeitet wurde. */
export interface ActivitySession {
  id: string
  project: string
  cwd: string
  title: string
  n: number
}

export interface ActivityProject {
  cwd: string
  /** Anzahl echter Eingaben an diesem Tag. */
  n: number
  sessions: ActivitySession[]
}

/** Tagebuch: Tag → Projekte, nach Eingaben absteigend (aus den Transkripten abgeleitet). */
export type Activity = Record<string, ActivityProject[]>

const EVENTS = ['events'] as const

export const useEvents = () =>
  useQuery({
    queryKey: EVENTS,
    queryFn: () => apiGet<CalEvent[]>('/api/events'),
    // Termine schreibt auch der Assistent (cal.py) — beim Öffnen immer frisch holen.
    refetchOnMount: 'always',
  })

export const useActivity = (start: string, end: string) =>
  useQuery({
    queryKey: ['activity', start, end],
    queryFn: () => apiGet<Activity>(`/api/activity?start=${start}&end=${end}`),
    // Heute kann beim nächsten Öffnen Neues dazugekommen sein.
    refetchOnMount: 'always',
  })

export function useAddEvent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ev: NewEvent) => apiPost<CalEvent>('/api/events', ev),
    onSettled: () => qc.invalidateQueries({ queryKey: EVENTS }),
  })
}

export function useDeleteEvent() {
  const qc = useQueryClient()
  return useMutation({
    // lib/api kennt kein DELETE — apiGet reicht init einfach an fetch durch.
    mutationFn: (id: string) =>
      apiDelete<{ deleted: number }>(`/api/events/${encodeURIComponent(id)}`),
    onSettled: () => qc.invalidateQueries({ queryKey: EVENTS }),
  })
}
