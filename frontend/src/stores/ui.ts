import { create } from 'zustand'

// Reiner Oberflächenzustand, der Ansichtswechsel überleben soll: die
// Seitenleiste auf schmalen Bildschirmen und die Filter der Sitzungsliste.
interface UiStore {
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
  sideOpen: false,
  setSideOpen: (sideOpen) => set({ sideOpen }),
  sessQuery: '',
  closedFolders: {},
  showArchived: false,
  showAgents: false,
  setSess: (p) => set(p),
}))
