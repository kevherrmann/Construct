import { create } from 'zustand'
import { queryClient } from '@/lib/queryClient'

// Sichtbarkeit der Update-Karte unten rechts. Eigener kleiner Store, weil
// auch ⚙ → "Jetzt suchen" die Karte wieder hervorholt — selbst wenn sie
// vorher weggeklickt wurde, und ohne auf ihren 60-s-Takt zu warten.
interface UpdateCardStore {
  hidden: boolean
  /** Einmal laufen gesehen? Nur dann gibt es etwas zu melden. */
  seen: boolean
  hide: () => void
  markSeen: () => void
  reveal: () => void
}

export const useUpdateCard = create<UpdateCardStore>((set) => ({
  hidden: false,
  seen: false,
  hide: () => set({ hidden: true }),
  markSeen: () => set({ seen: true }),
  reveal: () => {
    set({ hidden: false, seen: true })
    void queryClient.invalidateQueries({ queryKey: ['updates'] })
  },
}))
