import { bcdSpalten } from './binaer'

it('zerlegt HH:MM:SS in BCD-Spalten', () => {
  const sp = bcdSpalten(new Date(2026, 9, 5, 23, 59, 7))
  expect(sp.map((x) => x.wert)).toEqual([2, 3, 5, 9, 0, 7])
  expect(sp.map((x) => x.bits)).toEqual([2, 4, 3, 4, 3, 4])
})

it('jede Ziffer passt in ihre Bits', () => {
  for (let h = 0; h < 24; h++)
    for (const m of [0, 9, 10, 59]) {
      for (const sp of bcdSpalten(new Date(2026, 0, 1, h, m, m))) {
        expect(sp.wert).toBeLessThan(2 ** sp.bits)
        expect(sp.wert).toBeLessThanOrEqual(9)
      }
    }
})
