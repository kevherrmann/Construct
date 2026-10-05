import { useSyncExternalStore } from 'react'

/** Handy, Tablet hochkant, kleine Fenster: dort wird der Raum zum Panorama
 *  und Stationen öffnen als Karte von unten. Gleiche Grenze wie im CSS. */
export const KOMPAKT = '(max-width: 860px), (max-height: 520px)'

/** Trifft die Media Query zu? Aktualisiert sich bei Drehen und Größenänderung. */
export function useMedien(query: string): boolean {
  return useSyncExternalStore(
    (melde) => {
      if (typeof matchMedia !== 'function') return () => {}
      const mq = matchMedia(query)
      mq.addEventListener('change', melde)
      return () => mq.removeEventListener('change', melde)
    },
    () => typeof matchMedia === 'function' && matchMedia(query).matches,
    () => false,
  )
}
