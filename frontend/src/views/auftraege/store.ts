import { create } from 'zustand'

// Welcher Auftrag offen ist und was man darin ansieht. Bleibt beim Wechsel in
// andere Ansichten erhalten.
interface AuftraegeState {
  /** Auftrags-ID, 'neu' (Formular) oder null (nichts gewählt). */
  auswahl: string | 'neu' | null
  /** 'uebersicht' (Besetzung + Ergebnis), 'verlauf' (alle Nachrichten) oder der Slug einer Person. */
  sicht: string
  oeffne: (id: string) => void
  neu: () => void
  sichtWechseln: (sicht: string) => void
  schliessen: () => void
}

export const useAuftraegeAnsicht = create<AuftraegeState>((set) => ({
  auswahl: null,
  sicht: 'uebersicht',
  oeffne: (id) => set({ auswahl: id, sicht: 'uebersicht' }),
  neu: () => set({ auswahl: 'neu' }),
  sichtWechseln: (sicht) => set({ sicht }),
  schliessen: () => set({ auswahl: null, sicht: 'uebersicht' }),
}))
