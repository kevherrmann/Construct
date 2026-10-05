import { useState } from 'react'

/** Wo du die Sprechblase hingeschoben hast: linke und untere Kante in Prozent des
 *  Raums (die Blase zoomt mit der Kamera mit, Pixel würden beim Hineinfahren nicht
 *  passen). null = sie sucht sich ihren Platz selbst neben der Figur. */
export interface BlasenOrt {
  l: number
  b: number
}

const SCHLUESSEL = 'construct.raum.blase'

function lesen(): BlasenOrt | null {
  try {
    const o = JSON.parse(localStorage.getItem(SCHLUESSEL) ?? 'null') as BlasenOrt | null
    return o && Number.isFinite(o.l) && Number.isFinite(o.b) ? o : null
  } catch {
    return null
  }
}

export function useBlasenOrt() {
  const [ort, setOrt] = useState<BlasenOrt | null>(lesen)
  const setzen = (o: BlasenOrt | null) => {
    setOrt(o)
    try {
      if (o) localStorage.setItem(SCHLUESSEL, JSON.stringify(o))
      else localStorage.removeItem(SCHLUESSEL)
    } catch {
      /* privater Modus: dann gilt es nur bis zum Neuladen */
    }
  }
  return [ort, setzen] as const
}

/** Neue Lage beim Ziehen: Startlage plus Verschiebung, so begrenzt, dass die Blase
 *  ganz im Raum bleibt. Alles in Prozent des Raums. */
export function verschoben(
  start: BlasenOrt,
  dx: number,
  dy: number,
  groesse: { w: number; h: number },
): BlasenOrt {
  const zwischen = (v: number, max: number) => Math.min(Math.max(v, 0), Math.max(0, max))
  return {
    l: zwischen(start.l + dx, 100 - groesse.w),
    b: zwischen(start.b - dy, 100 - groesse.h),
  }
}
