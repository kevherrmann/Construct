import { useEffect, useRef } from 'react'

// Solange `active`, alle `ms` den Stand holen und weiterreichen — für Läufe,
// die am Server im Hintergrund arbeiten (Installation, Updates) und die die
// Oberfläche nur beobachtet. Fehler einzelner Abfragen werden übergangen:
// der nächste Takt versucht es wieder.
export function usePolling<T>(
  active: boolean,
  fetch: () => Promise<T>,
  onData: (d: T) => void,
  ms = 1200,
) {
  const cb = useRef({ fetch, onData })
  useEffect(() => {
    cb.current = { fetch, onData }
  })
  useEffect(() => {
    if (!active) return
    let alive = true
    const id = setInterval(async () => {
      try {
        const d = await cb.current.fetch()
        if (alive) cb.current.onData(d)
      } catch {
        /* nächster Takt */
      }
    }, ms)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [active, ms])
}
