import { useEffect, useRef, useState } from 'react'
import type { Helfer } from '@/lib/chat/types'
import { holosNach, naechsteAenderung, type Holo } from './hologramme'

const KEINE: readonly Helfer[] = []

/** Hologramme zu den Helfern einer Quelle (Unterhaltung, Zug). Wechselt die Quelle,
 *  verschwinden die alten ohne Zerfall: sie gehören nicht zu dem, was man jetzt sieht. */
export function useHologramme(helfer: readonly Helfer[] | undefined, quelle: string): Holo[] {
  const liste = helfer ?? KEINE
  const [stand, setStand] = useState<{ quelle: string; holos: Holo[] }>({ quelle, holos: [] })
  const aktuell = useRef(liste)
  useEffect(() => {
    aktuell.current = liste
    // im nächsten Takt: die Uhrzeit gehört nicht ins Zeichnen
    const id = setTimeout(() =>
      setStand((v) => {
        const basis = v.quelle === quelle ? v.holos : []
        const holos = holosNach(basis, liste, Date.now())
        return v.quelle === quelle && holos === v.holos ? v : { quelle, holos }
      }),
    )
    return () => clearTimeout(id)
  }, [liste, quelle])
  // Ohne neues Ereignis: zum Ende der laufenden Phase weiterschalten.
  useEffect(() => {
    const ms = naechsteAenderung(stand.holos, Date.now())
    if (ms === null) return
    const id = setTimeout(
      () =>
        setStand((v) => {
          const holos = holosNach(v.holos, aktuell.current, Date.now())
          return holos === v.holos ? v : { ...v, holos }
        }),
      ms + 16,
    )
    return () => clearTimeout(id)
  }, [stand])
  return stand.quelle === quelle ? stand.holos : []
}
