import { create } from 'zustand'

// Was die Personal-Ansicht gerade zeigt. Bleibt beim Wechsel in andere
// Ansichten erhalten.
export type PersonalAnsicht = 'org' | 'akte' | 'user'

interface PersonalState {
  ansicht: PersonalAnsicht
  /** Slug der geöffneten Akte (nur bei ansicht = 'akte'). */
  slug: string | null
  zeigeOrg: () => void
  zeigeAkte: (slug: string) => void
  zeigeUser: () => void
}

export const usePersonal = create<PersonalState>((set) => ({
  ansicht: 'org',
  slug: null,
  zeigeOrg: () => set({ ansicht: 'org', slug: null }),
  zeigeAkte: (slug) => set({ ansicht: 'akte', slug }),
  zeigeUser: () => set({ ansicht: 'user', slug: null }),
}))
