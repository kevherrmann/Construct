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
const HOEHE = 'construct.raum.blase.hoehe'

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

/** Kompakt (Bodenblatt unter 861 px): nur die Höhe, bis zu der sie wächst, in
 *  Prozent der Raumhöhe. Eigener Schlüssel: auf dem Handy passt die Desktop-Größe nicht. */
export function useBlasenHoehe() {
  return useGemerkt<{ h: number }>(HOEHE, ['h'])
}

export const zwischen = (v: number, min: number, max: number) =>
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

/** Lage und Größe zusammen, alles in Prozent des Raums. */
export type BlasenRahmen = BlasenOrt & BlasenGroesse

/** Woran gezogen wird: x −1 = linke Kante, 1 = rechte; y −1 = obere, 1 = untere;
 *  0 = diese Richtung bleibt. Eine Ecke hat beides. */
export interface Kante {
  x: -1 | 0 | 1
  y: -1 | 0 | 1
}

/** Bis dahin reicht die Blase beim Aufziehen: rechts und oben ein wenig Luft. */
const RECHTS = 99
const OBEN = 98

/** Neuer Rahmen beim Ziehen an einer Kante oder Ecke: die gegenüberliegende Kante
 *  bleibt stehen, wie bei einem Fenster. Begrenzt auf min/max und den Raum. */
export function aufgezogen(
  start: BlasenRahmen,
  kante: Kante,
  dx: number,
  dy: number,
  min: BlasenGroesse,
  max: BlasenGroesse,
): BlasenRahmen {
  let { l, b, w, h } = start
  if (kante.x === 1) w = zwischen(w + dx, min.w, Math.min(max.w, RECHTS - l))
  if (kante.x === -1) {
    const r = l + w
    w = zwischen(w - dx, min.w, Math.min(max.w, r))
    l = r - w
  }
  if (kante.y === -1) h = zwischen(h - dy, min.h, Math.min(max.h, OBEN - b))
  if (kante.y === 1) {
    const o = b + h
    h = zwischen(h + dy, min.h, Math.min(max.h, o))
    b = o - h
  }
  return { l, b, w, h }
}

/** Höchstens so hoch, dass der Kopf im Raum bleibt (sonst kommst du nicht mehr
 *  an ihn heran, um sie zurückzuschieben). */
export const hoechstens = (h: number, b: number) => Math.min(h, OBEN - b)
