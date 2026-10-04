import { create } from 'zustand'
import { getItem, setItem } from '@/lib/storage'

// Reiner Oberflächenzustand, der Ansichtswechsel überleben soll: die
// Seitenleiste auf schmalen Bildschirmen und die Filter der Sitzungsliste.
interface UiStore {
  /** Construct-Raum statt Chat-Ansicht (gemerkt). */
  raum: boolean
  setRaum: (on: boolean) => void
  sideOpen: boolean
  setSideOpen: (open: boolean) => void
  sessQuery: string
  closedFolders: Record<string, boolean>
  showArchived: boolean
  showAgents: boolean
  setSess: (
    p: Partial<Pick<UiStore, 'sessQuery' | 'closedFolders' | 'showArchived' | 'showAgents'>>,
  ) => void
}

export const useUi = create<UiStore>((set) => ({
  raum: getItem('mxraum') === '1',
  setRaum: (raum) => {
    setItem('mxraum', raum ? '1' : null)
    set({ raum })
  },
  sideOpen: false,
  setSideOpen: (sideOpen) => set({ sideOpen }),
  sessQuery: '',
  closedFolders: {},
  showArchived: false,
  showAgents: false,
  setSess: (p) => set(p),
}))
