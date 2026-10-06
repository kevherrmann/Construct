import { useState } from 'react'

/** Wo du die Sprechblase hingeschoben hast: linke und untere Kante in Prozent des
 *  Raums (die Blase zoomt mit der Kamera mit, Pixel würden beim Hineinfahren nicht
 *  passen). null = sie sucht sich ihren Platz selbst neben der Figur. */
export interface BlasenOrt {
  l: number
  b: number
}

/** Wie groß du sie gezogen hast, ebenfalls in Prozent des Raums: Breite und die
 *  Höhe, bis zu der sie wächst (kurze Antworten bleiben kurz). null = Vorgabe. */
export interface BlasenGroesse {
  w: number
  h: number
}

const ORT = 'construct.raum.blase'
const GROESSE = 'construct.raum.blase.groesse'

function lesen<T>(schluessel: string, felder: (keyof T)[]): T | null {
  try {
    const o = JSON.parse(localStorage.getItem(schluessel) ?? 'null') as T | null
    return o && felder.every((f) => Number.isFinite(o[f])) ? o : null
  } catch {
    return null
  }
}

function useGemerkt<T>(schluessel: string, felder: (keyof T)[]) {
  const [wert, setWert] = useState<T | null>(() => lesen<T>(schluessel, felder))
  const setzen = (o: T | null) => {
    setWert(o)
    try {
      if (o) localStorage.setItem(schluessel, JSON.stringify(o))
      else localStorage.removeItem(schluessel)
    } catch {
      /* privater Modus: dann gilt es nur bis zum Neuladen */
    }
  }
  return [wert, setzen] as const
}

export function useBlasenOrt() {
  return useGemerkt<BlasenOrt>(ORT, ['l', 'b'])
}

export function useBlasenGroesse() {
  return useGemerkt<BlasenGroesse>(GROESSE, ['w', 'h'])
}

const zwischen = (v: number, min: number, max: number) =>
  Math.min(Math.max(v, min), Math.max(min, max))

/** Neue Lage beim Ziehen: Startlage plus Verschiebung, so begrenzt, dass die Blase
 *  ganz im Raum bleibt. Alles in Prozent des Raums. */
export function verschoben(
  start: BlasenOrt,
  dx: number,
  dy: number,
  groesse: { w: number; h: number },
): BlasenOrt {
  return {
    l: zwischen(start.l + dx, 0, 100 - groesse.w),
    b: zwischen(start.b - dy, 0, 100 - groesse.h),
  }
}

/** Neue Größe beim Ziehen am Griff oben rechts: nach rechts breiter, nach oben höher
 *  (die Blase hängt unten fest, der Zipfel bleibt bei der Figur). Begrenzt auf
 *  min/max — max ist zugleich der Platz bis zum Rand des Raums. */
export function vergroessert(
  start: BlasenGroesse,
  dx: number,
  dy: number,
  min: BlasenGroesse,
  max: BlasenGroesse,
): BlasenGroesse {
  return {
    w: zwischen(start.w + dx, min.w, max.w),
    h: zwischen(start.h - dy, min.h, max.h),
  }
}
