import { create } from 'zustand'

// Welcher Dialog gerade offen ist. Von überall aufrufbar (Befehle, Menüs,
// HUD) — gezeichnet werden die Dialoge einmal im AppShell.
export type DialogName = 'providers' | 'login'

interface DialogStore {
  current: DialogName | null
  open: (d: DialogName) => void
  close: () => void
}

export const useDialogs = create<DialogStore>((set) => ({
  current: null,
  open: (d) => set({ current: d }),
  close: () => set({ current: null }),
}))
