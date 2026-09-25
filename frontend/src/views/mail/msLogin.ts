import { create } from 'zustand'
import { MAIL_KEYS, mailApi } from '@/api/mail'
import { queryClient } from '@/lib/queryClient'

// Microsoft-Anmeldung (Gerätecode). Erst der Abfrage-Takt (ms_poll) legt das
// Refresh-Token auf dem Server ab — er muss darum weiterlaufen, auch wenn man
// die Kontoseite verlässt, während man den Code bei Microsoft eingibt. Wie in
// der alten Oberfläche endet er nur bei Erfolg oder Fehler.

export type MsState =
  | { phase: 'wait'; url: string; code: string }
  | { phase: 'ok' }
  | { phase: 'error'; message: string }

const POLL_MS = 5000
const timers = new Map<string, ReturnType<typeof setInterval>>()

interface MsLoginStore {
  byAccount: Record<string, MsState>
  start: (email: string, url: string, code: string) => void
  /** Anzeige verwerfen (z. B. wenn danach TEST geklickt wird). */
  clear: (email: string) => void
}

export const useMsLogin = create<MsLoginStore>((set) => {
  const put = (email: string, st: MsState) =>
    set((s) => ({ byAccount: { ...s.byAccount, [email]: st } }))
  const stop = (email: string) => {
    clearInterval(timers.get(email))
    timers.delete(email)
  }
  return {
    byAccount: {},
    start(email, url, code) {
      stop(email)
      put(email, { phase: 'wait', url, code })
      timers.set(
        email,
        setInterval(async () => {
          try {
            const p = await mailApi.msPoll(email)
            if ('ok' in p) {
              stop(email)
              put(email, { phase: 'ok' })
              void queryClient.invalidateQueries({ queryKey: MAIL_KEYS.accounts })
              // Liste nur als veraltet markieren — neu geladen wird beim nächsten Öffnen.
              void queryClient.invalidateQueries({ queryKey: MAIL_KEYS.list, refetchType: 'none' })
            } else if ('error' in p) {
              stop(email)
              put(email, { phase: 'error', message: p.error })
            }
          } catch {
            /* Netzaussetzer — beim nächsten Takt nochmal */
          }
        }, POLL_MS),
      )
    },
    clear(email) {
      set((s) => {
        const byAccount = { ...s.byAccount }
        delete byAccount[email]
        return { byAccount }
      })
    },
  }
})
