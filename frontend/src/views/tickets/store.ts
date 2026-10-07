import { create } from 'zustand'

// Welches Projekt das Board zeigt und welche Karte offen ist. Bleibt beim
// Wechsel in andere Ansichten erhalten.
interface TicketsState {
  /** Pfad des Projekts; null = alle. */
  projekt: string | null
  /** Offene Karte: Nummer, 'neu' für eine neue, null = keine. */
  offen: number | 'neu' | null
  setProjekt: (p: string | null) => void
  oeffne: (nr: number | 'neu') => void
  zu: () => void
}

export const useTicketsAnsicht = create<TicketsState>((set) => ({
  projekt: null,
  offen: null,
  setProjekt: (projekt) => set({ projekt }),
  oeffne: (offen) => set({ offen }),
  zu: () => set({ offen: null }),
}))
