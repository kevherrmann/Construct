// Ziffern der Tetris-Uhr als fallende Tetrominos — eigene Datei, damit testbar.
//
// Schnittstelle:
//   tetrisZiffern(d)  → 4 Ziffern (H, H, M, M; Sekunden zählen nicht), je { wert, steine }.
//   zifferSteine(w)   → die Steine der Ziffer w, in Fallreihenfolge.
//   Stein             → { typ, drehung, x, y, zellen }. Raster ZIFFER_BREITE × ZIFFER_HOEHE,
//                       y = 0 ist oben. (x, y) ist die linke obere Ecke des Steins am Ziel,
//                       zellen = formZellen(typ, drehung) um (x, y) verschoben.
//   formZellen(t, n)  → Zellen eines Steins nach n Vierteldrehungen im Uhrzeigersinn,
//                       links oben bündig; für Zwischenstufen, wenn er im Fall dreht.
//
// Fallreihenfolge: lässt man die Steine in dieser Reihenfolge senkrecht von oben fallen,
// rastet jeder genau an seinem Ziel ein (auf dem Boden oder auf schon liegenden Steinen),
// und der Weg darüber ist frei. Gedreht wird also oberhalb des Rasters.

export type Typ = 'I' | 'O' | 'T' | 'S' | 'Z' | 'J' | 'L'

export interface Zelle {
  x: number
  y: number
}

export interface Stein {
  typ: Typ
  /** Vierteldrehungen im Uhrzeigersinn gegenüber der Grundform, 0–3. */
  drehung: number
  x: number
  y: number
  zellen: readonly Zelle[]
}

export interface TetrisZiffer {
  wert: number
  steine: readonly Stein[]
}

export const ZIFFER_BREITE = 4
export const ZIFFER_HOEHE = 7

// Grundformen wie beim Erscheinen im echten Tetris.
const GRUNDFORM: Record<Typ, readonly string[]> = {
  I: ['####'],
  O: ['##', '##'],
  T: ['.#.', '###'],
  S: ['.##', '##.'],
  Z: ['##.', '.##'],
  J: ['#..', '###'],
  L: ['..#', '###'],
}

export const TYPEN = Object.keys(GRUNDFORM) as Typ[]

// Feste Zerlegung je Ziffer: gleicher Buchstabe = ein Stein, a fällt zuerst, dann b, …
// Typ und Drehung ergeben sich aus der Form. Gefunden per Suche, die das Schweben ausschließt.
const ZERLEGUNG: readonly (readonly string[])[] = [
  ['eeee', 'dd.c', 'd..c', 'd..c', 'a..c', 'a.bb', 'aabb'],
  ['..b.', '.bb.', '..b.', '..a.', '..a.', '..a.', '..a.'],
  ['.ddd', '...d', '...c', 'bccc', 'bb..', 'b...', 'aaaa'],
  ['.ddd', '...d', '...c', '.ccc', '..bb', 'a..b', 'aaab'],
  ['c..d', 'c..d', 'ccdd', 'bbbb', '...a', '...a', '..aa'],
  ['ddd.', 'd...', 'c...', 'cccb', '..bb', '...b', 'aaaa'],
  ['dd..', 'd...', 'd...', 'cccc', 'a..b', 'a..b', 'aabb'],
  ['cccc', '.bbb', '...b', '...a', '...a', '...a', '...a'],
  ['eeee', 'c..d', 'c..d', 'ccdd', 'a..b', 'a..b', 'aabb'],
  ['ccdd', 'c..d', 'c..d', 'bbbb', '...a', '...a', '..aa'],
]

function buendig(zellen: readonly Zelle[]): Zelle[] {
  const minX = Math.min(...zellen.map((z) => z.x))
  const minY = Math.min(...zellen.map((z) => z.y))
  return zellen
    .map((z) => ({ x: z.x - minX, y: z.y - minY }))
    .sort((a, b) => a.y - b.y || a.x - b.x)
}

function gleich(a: readonly Zelle[], b: readonly Zelle[]): boolean {
  return a.length === b.length && a.every((z, i) => z.x === b[i]?.x && z.y === b[i]?.y)
}

export function formZellen(typ: Typ, drehung: number): Zelle[] {
  let zellen: Zelle[] = []
  GRUNDFORM[typ].forEach((zeile, y) =>
    [...zeile].forEach((ch, x) => {
      if (ch === '#') zellen.push({ x, y })
    }),
  )
  // Bildschirmkoordinaten (y nach unten): (x, y) → (−y, x) ist eine Vierteldrehung im Uhrzeigersinn.
  for (let n = 0; n < ((drehung % 4) + 4) % 4; n++)
    zellen = zellen.map((z) => ({ x: -z.y, y: z.x }))
  return buendig(zellen)
}

function erkenne(zellen: readonly Zelle[]): { typ: Typ; drehung: number } {
  const form = buendig(zellen)
  for (const typ of TYPEN)
    for (let drehung = 0; drehung < 4; drehung++)
      if (gleich(formZellen(typ, drehung), form)) return { typ, drehung }
  throw new Error(`kein Tetromino: ${JSON.stringify(form)}`)
}

function zerlege(zeilen: readonly string[]): Stein[] {
  const nachBuchstabe = new Map<string, Zelle[]>()
  zeilen.forEach((zeile, y) =>
    [...zeile].forEach((ch, x) => {
      if (ch === '.') return
      const liste = nachBuchstabe.get(ch) ?? []
      liste.push({ x, y })
      nachBuchstabe.set(ch, liste)
    }),
  )
  // Zellen kommen zeilenweise herein, also schon in derselben Ordnung wie bei formZellen.
  return [...nachBuchstabe.keys()].sort().map((ch) => {
    const zellen = nachBuchstabe.get(ch) ?? []
    const x = Math.min(...zellen.map((z) => z.x))
    const y = Math.min(...zellen.map((z) => z.y))
    return { ...erkenne(zellen), x, y, zellen }
  })
}

const STEINE: readonly (readonly Stein[])[] = ZERLEGUNG.map(zerlege)

export function zifferSteine(wert: number): readonly Stein[] {
  const steine = STEINE[wert]
  if (!steine) throw new Error(`keine Ziffer: ${wert}`)
  return steine
}

export function tetrisZiffern(d: Date): TetrisZiffer[] {
  const [h, m] = [d.getHours(), d.getMinutes()]
  return [Math.floor(h / 10), h % 10, Math.floor(m / 10), m % 10].map((wert) => ({
    wert,
    steine: zifferSteine(wert),
  }))
}
