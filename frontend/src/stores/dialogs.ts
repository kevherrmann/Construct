import { create } from 'zustand'
import type { AuthStatus } from '@/api/system'

// Welche App-weite Dialogbox gerade offen ist. Gerendert werden sie einmal im
// AppShell; öffnen kann sie jeder: useDialogs.getState().open('providers').
//   providers  KI-Anbieter (Keys, Ollama, Bonsai)
//   login      Claude-Web-Login (setup-token)
//   claude     Anleitung: Claude Code installieren / im Terminal anmelden
export type DialogName = 'providers' | 'login' | 'claude'

interface DialogStore {
  current: DialogName | null
  open: (d: DialogName) => void
  close: () => void
}

export const useDialogs = create<DialogStore>((set) => ({
  current: null,
  open: (current) => set({ current }),
  close: () => set({ current: null }),
}))

export const openDialog = (d: DialogName) => useDialogs.getState().open(d)

/**
 * Der 🔑-Knopf führt dahin, wo der Nutzer gerade steht: Web-Login, wenn
 * Claude Code da ist und das Pseudo-Terminal geht (nicht unter Windows) —
 * sonst die Anleitung zum Installieren bzw. Anmelden im Terminal.
 */
export function authTarget(auth: Pick<AuthStatus, 'cli' | 'can_web_login'> | undefined) {
  return auth && auth.cli !== false && auth.can_web_login ? 'login' : 'claude'
}

export const openClaudeAuth = (auth: Pick<AuthStatus, 'cli' | 'can_web_login'> | undefined) =>
  openDialog(authTarget(auth))
