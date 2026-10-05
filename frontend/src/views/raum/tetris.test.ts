import {
  formZellen,
  tetrisZiffern,
  zifferSteine,
  ZIFFER_BREITE,
  ZIFFER_HOEHE,
  type Zelle,
} from './tetris'

// Soll-Formen der Ziffern, unabhängig von der Zerlegung: so muss die Uhr aussehen.
const FORM = [
  ['####', '##.#', '#..#', '#..#', '#..#', '#.##', '####'],
  ['..#.', '.##.', '..#.', '..#.', '..#.', '..#.', '..#.'],
  ['.###', '...#', '...#', '####', '##..', '#...', '####'],
  ['.###', '...#', '...#', '.###', '..##', '#..#', '####'],
  ['#..#', '#..#', '####', '####', '...#', '...#', '..##'],
  ['###.', '#...', '#...', '####', '..##', '...#', '####'],
  ['##..', '#...', '#...', '####', '#..#', '#..#', '####'],
  ['####', '.###', '...#', '...#', '...#', '...#', '...#'],
  ['####', '#..#', '#..#', '####', '#..#', '#..#', '####'],
  ['####', '#..#', '#..#', '####', '...#', '...#', '..##'],
]

// Alle Lagen der sieben Tetrominos, hier eigens aufgeschrieben statt aus tetris.ts übernommen.
const LAGEN: Record<string, string[][]> = {
  I: [['####'], ['#', '#', '#', '#']],
  O: [['##', '##']],
  T: [
    ['.#.', '###'],
    ['#.', '##', '#.'],
    ['###', '.#.'],
    ['.#', '##', '.#'],
  ],
  S: [
    ['.##', '##.'],
    ['#.', '##', '.#'],
  ],
  Z: [
    ['##.', '.##'],
    ['.#', '##', '#.'],
  ],
  J: [
    ['#..', '###'],
    ['##', '#.', '#.'],
    ['###', '..#'],
    ['.#', '.#', '##'],
  ],
  L: [
    ['..#', '###'],
    ['#.', '#.', '##'],
    ['###', '#..'],
    ['##', '.#', '.#'],
  ],
}

const schluessel = (z: Zelle) => `${z.x},${z.y}`

function bild(zellen: readonly Zelle[]): string[] {
  const breite = Math.max(...zellen.map((z) => z.x)) + 1
  const hoehe = Math.max(...zellen.map((z) => z.y)) + 1
  const belegt = new Set(zellen.map(schluessel))
  return Array.from({ length: hoehe }, (_, y) =>
    Array.from({ length: breite }, (_, x) => (belegt.has(`${x},${y}`) ? '#' : '.')).join(''),
  )
}

function verschoben(zellen: readonly Zelle[], dx: number, dy: number): Zelle[] {
  return zellen.map((z) => ({ x: z.x + dx, y: z.y + dy }))
}

const ZIFFERN = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

it.each(ZIFFERN)('Ziffer %i besteht nur aus echten Tetrominos', (w) => {
  for (const s of zifferSteine(w)) {
    expect(s.zellen).toHaveLength(4)
    const form = bild(verschoben(s.zellen, -s.x, -s.y))
    expect(LAGEN[s.typ]).toContainEqual(form)
    expect(s.zellen).toEqual(verschoben(formZellen(s.typ, s.drehung), s.x, s.y))
  }
})

it.each(ZIFFERN)('Steine der Ziffer %i decken genau ihre Form ab, ohne Doppel', (w) => {
  const alle = zifferSteine(w).flatMap((s) => s.zellen)
  expect(new Set(alle.map(schluessel)).size).toBe(alle.length)
  for (const z of alle) {
    expect(z.x).toBeGreaterThanOrEqual(0)
    expect(z.x).toBeLessThan(ZIFFER_BREITE)
    expect(z.y).toBeGreaterThanOrEqual(0)
    expect(z.y).toBeLessThan(ZIFFER_HOEHE)
  }
  const soll = FORM[w] ?? []
  const ist = Array.from({ length: ZIFFER_HOEHE }, (_, y) =>
    Array.from({ length: ZIFFER_BREITE }, (_, x) =>
      alle.some((z) => z.x === x && z.y === y) ? '#' : '.',
    ).join(''),
  )
  expect(ist).toEqual(soll)
})

it.each(ZIFFERN)('Ziffer %i fällt wie im Tetris: jeder Stein landet genau am Ziel', (w) => {
  const liegt = new Set<string>()
  for (const s of zifferSteine(w)) {
    // Von ganz oben senkrecht fallen lassen, bis Boden oder Stein darunter.
    let dy = -ZIFFER_HOEHE - 4
    const frei = (d: number) =>
      verschoben(s.zellen, 0, d).every((z) => z.y < ZIFFER_HOEHE && !liegt.has(schluessel(z)))
    while (frei(dy + 1)) dy++
    expect(dy).toBe(0)
    for (const z of s.zellen) liegt.add(schluessel(z))
  }
})

it('Drehung 4 ist wieder die Grundform, die Formen sind links oben bündig', () => {
  for (const typ of ['I', 'O', 'T', 'S', 'Z', 'J', 'L'] as const)
    for (let n = 0; n < 4; n++) {
      const f = formZellen(typ, n)
      expect(Math.min(...f.map((z) => z.x))).toBe(0)
      expect(Math.min(...f.map((z) => z.y))).toBe(0)
      expect(formZellen(typ, n + 4)).toEqual(f)
    }
})

it('zerlegt HH:MM ohne Sekunden', () => {
  const z = tetrisZiffern(new Date(2026, 9, 5, 23, 59, 7))
  expect(z.map((x) => x.wert)).toEqual([2, 3, 5, 9])
  expect(z.map((x) => x.steine)).toEqual([2, 3, 5, 9].map(zifferSteine))
  expect(tetrisZiffern(new Date(2026, 9, 5, 23, 59, 58))).toEqual(z)

  const null0 = tetrisZiffern(new Date(2026, 9, 6, 0, 0, 0))
  expect(null0.map((x) => x.wert)).toEqual([0, 0, 0, 0])
  expect(null0[0]?.steine.map((s) => s.typ)).toEqual(['L', 'O', 'I', 'J', 'I'])
})

it('unbekannte Ziffer ist ein Fehler', () => {
  expect(() => zifferSteine(10)).toThrow()
})
