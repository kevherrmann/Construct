import { ago, fmtGB, pct } from './format'

it('fmtGB', () => {
  expect(fmtGB(9_600_000_000)).toBe('9,6 GB')
  expect(fmtGB(815_000_000)).toBe('815 MB')
  expect(fmtGB(0)).toBe('0 MB')
})

it('pct', () => {
  expect(pct({ total: 0, completed: 5 })).toBe(0)
  expect(pct({ total: 200, completed: 51 })).toBe(26)
})

it('ago', () => {
  expect(ago(1000, 1010)).toEqual({ unit: 'now', n: 0 })
  expect(ago(1000, 1000 + 5 * 60)).toEqual({ unit: 'min', n: 5 })
  expect(ago(1000, 1000 + 3 * 3600)).toEqual({ unit: 'h', n: 3 })
})
