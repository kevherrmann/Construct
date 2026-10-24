import { create } from 'zustand'
import type { Filter } from '@/api/dokumente'

export const OHNE_FILTER: Filter = {
  q: '',
  jahr: '',
  absender: null,
  typ: null,
  tag: null,
  eingang: null,
}

// Was die Dokumente-Ansicht zeigt: Filter, offenes Dokument, Scan-Dialog.
// Bleibt beim Wechsel in andere Ansichten erhalten.
interface DokumenteState {
  filter: Filter
  /** Dokument rechts im Detail; null = nur Liste. */
  offen: number | null
  scannen: boolean
  setFilter: (f: Partial<Filter>) => void
  /** Ein Bereich der Seitenleiste: ersetzt alle Filter außer der Suche. */
  bereich: (f: Partial<Filter>) => void
  oeffne: (id: number | null) => void
  setScannen: (an: boolean) => void
}

export const useDokumenteAnsicht = create<DokumenteState>((set) => ({
  filter: { ...OHNE_FILTER, eingang: true },
  offen: null,
  scannen: false,
  setFilter: (f) => set((st) => ({ filter: { ...st.filter, ...f } })),
  bereich: (f) => set((st) => ({ filter: { ...OHNE_FILTER, q: st.filter.q, ...f }, offen: null })),
  oeffne: (offen) => set({ offen }),
  setScannen: (scannen) => set({ scannen }),
}))
