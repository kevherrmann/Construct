import type { Element } from '@/api/dokumente'
import { getItem, setItem } from '@/lib/storage'

const ORT = 'construct.unterschrift.ort'

const auf = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v))

export const heute = (d = new Date()) =>
  `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`

/** „Lengerich, 05.11.2026“: der Ort vom letzten Mal, das Datum von heute. */
export const ortDatum = (ort: string | null, d = new Date()) =>
  ort ? `${ort}, ${heute(d)}` : heute(d)

export const ortHolen = () => getItem(ORT)

/** Steht in einem Text „Ort, TT.MM.JJJJ“, den Ort fürs nächste Mal merken. */
export function ortMerken(elemente: Element[]) {
  for (const e of elemente) {
    const m = e.art === 'text' ? /^(.+?),\s*\d{1,2}\.\d{1,2}\.\d{2,4}$/.exec(e.text.trim()) : null
    if (m?.[1]) {
      setItem(ORT, m[1].trim())
      return
    }
  }
}

/** Verschieben, aber nie ganz von der Seite: ein Rest bleibt greifbar. */
export function verschoben(e: Element, dx: number, dy: number): Element {
  return { ...e, x: auf(e.x + dx, -0.05, 0.97), y: auf(e.y + dy, -0.02, 0.98) }
}

/** Größe über den Griff unten rechts: Unterschrift nach Breite, Text nach Schriftgröße. */
export function vergroessert(
  e: Element,
  dx: number,
  seite: { breite: number; hoehe: number },
): Element {
  if (e.art === 'unterschrift') return { ...e, breite: auf(e.breite + dx, 0.05, 0.9) }
  // Text: Breite folgt der Schrift; ~0,5 Zeichenbreiten je Punkt Schriftgröße
  const zeichen = Math.max(4, e.text.length) * 0.5
  const neu = e.hoehe + (dx * seite.breite) / zeichen / seite.hoehe
  return { ...e, hoehe: auf(neu, 4 / seite.hoehe, 40 / seite.hoehe) }
}
