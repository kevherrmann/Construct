import { create } from 'zustand'

// Welcher Tag (und welches Projekt) in der Ticket-Übersicht offen ist.
// Bleibt beim Wechsel in andere Ansichten erhalten.
interface TicketsState {
  /** YYYY-MM-DD; null = der jüngste Tag mit Tickets. */
  tag: string | null
  /** Arbeitsordner; null = alle Projekte des Tages. */
  cwd: string | null
  wahl: (tag: string | null, cwd?: string | null) => void
}

export const useTicketsAnsicht = create<TicketsState>((set) => ({
  tag: null,
  cwd: null,
  wahl: (tag, cwd = null) => set({ tag, cwd }),
}))
