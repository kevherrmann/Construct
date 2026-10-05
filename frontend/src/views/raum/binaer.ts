// Ziffern der Binäruhr (BinaerUhr.tsx) als Bits — eigene Datei, damit testbar.

export interface Spalte {
  /** Wert der Ziffer, 0–9. */
  wert: number
  /** Wie viele Bits die Ziffer höchstens braucht (2, 3 oder 4). */
  bits: number
}

export const ZEILEN = [8, 4, 2, 1] as const

export function bcdSpalten(d: Date): Spalte[] {
  const [h, m, sek] = [d.getHours(), d.getMinutes(), d.getSeconds()]
  return [
    { wert: Math.floor(h / 10), bits: 2 },
    { wert: h % 10, bits: 4 },
    { wert: Math.floor(m / 10), bits: 3 },
    { wert: m % 10, bits: 4 },
    { wert: Math.floor(sek / 10), bits: 3 },
    { wert: sek % 10, bits: 4 },
  ]
}
