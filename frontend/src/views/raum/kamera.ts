// Kamera des Construct-Raums: statt Fenster über dem Raum fährt die Kamera an
// die Station heran, der Inhalt erscheint daneben im Weiß. Alles in Prozent
// der Bühne, damit es mit ihr skaliert.

export type Punkt = readonly [number, number]

export interface Kamera {
  /** Zoom (1 = ganzer Raum). */
  z: number
  /** Punkt im Raum (Prozent), der an Stelle `p` des Bildschirms landen soll. */
  f: Punkt
  p: Punkt
}

export const GANZ: Kamera = { z: 1, f: [50, 50], p: [50, 50] }

/** Verschiebung der Welt (Prozent) für eine Kamera. Die Welt deckt die Bühne
 *  immer ganz ab — am Rand bleibt die Kamera lieber stehen, als Leere zu zeigen. */
export function verschiebung(k: Kamera): Punkt {
  const achse = (i: 0 | 1) => Math.min(0, Math.max(100 - 100 * k.z, k.p[i] - k.z * k.f[i]))
  return [achse(0), achse(1)]
}

/** CSS-Transform der Welt (transform-origin: 0 0). */
export function weltTransform(k: Kamera): string {
  const [x, y] = verschiebung(k)
  return `translate(${x}%, ${y}%) scale(${k.z})`
}

/** Wo ein Punkt des Raums nach der Kamerafahrt auf der Bühne liegt. */
export function aufBuehne(k: Kamera, q: Punkt): Punkt {
  const [x, y] = verschiebung(k)
  return [x + k.z * q[0], y + k.z * q[1]]
}

/** Viereck in Pixeln: oben links, oben rechts, unten rechts, unten links. */
export type Viereck = readonly [Punkt, Punkt, Punkt, Punkt]

/**
 * matrix3d, die ein Rechteck w×h (transform-origin 0 0) perspektivisch auf ein
 * Viereck legt — damit steht der Terminal-Text wirklich auf der Monitorwand.
 * Projektive Abbildung Einheitsquadrat → Viereck (Heckbert), dann auf w×h skaliert.
 */
export function viereckMatrix(w: number, h: number, q: Viereck): string {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = q
  const dx1 = x1 - x2
  const dx2 = x3 - x2
  const dx3 = x0 - x1 + x2 - x3
  const dy1 = y1 - y2
  const dy2 = y3 - y2
  const dy3 = y0 - y1 + y2 - y3
  let g = 0
  let hh = 0
  if (dx3 || dy3) {
    const det = dx1 * dy2 - dx2 * dy1
    g = (dx3 * dy2 - dx2 * dy3) / det
    hh = (dx1 * dy3 - dx3 * dy1) / det
  }
  const a = x1 - x0 + g * x1
  const b = x3 - x0 + hh * x3
  const d = y1 - y0 + g * y1
  const e = y3 - y0 + hh * y3
  const m = [a / w, d / w, 0, g / w, b / h, e / h, 0, hh / h, 0, 0, 1, 0, x0, y0, 0, 1]
  return `matrix3d(${m.map((v) => +v.toPrecision(12)).join(',')})`
}

/**
 * Flache Verzerrung (CSS matrix, ohne Perspektive) eines Rechtecks w×h auf ein
 * Parallelogramm: oben links, oben rechts, unten links. Für Schrift im Raum —
 * sieht in jeder Engine gleich aus (WebKitGTK ohne 3D-Ebenen ignoriert den
 * perspektivischen Anteil von matrix3d).
 */
export function parallelMatrix(w: number, h: number, ol: Punkt, or: Punkt, ul: Punkt): string {
  const m = [
    (or[0] - ol[0]) / w,
    (or[1] - ol[1]) / w,
    (ul[0] - ol[0]) / h,
    (ul[1] - ol[1]) / h,
    ol[0],
    ol[1],
  ]
  return `matrix(${m.map((v) => +v.toPrecision(10)).join(',')})`
}
