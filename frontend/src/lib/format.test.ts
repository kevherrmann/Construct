import { ago, fmtGB, fmtMsgTime, parseTs, pct } from './format'

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

it('parseTs: ISO-Text, Unix-Sekunden, Unsinn', () => {
  expect(parseTs('2026-09-29T19:14:00.000Z')).toBe(Date.UTC(2026, 8, 29, 19, 14))
  expect(parseTs(1_790_000_000)).toBe(1_790_000_000_000)
  expect(parseTs(1_790_000_000_000)).toBe(1_790_000_000_000)
  expect(parseTs('kaputt')).toBeUndefined()
  expect(parseTs(undefined)).toBeUndefined()
})

it('fmtMsgTime: heute nur Uhrzeit, sonst mit Datum', () => {
  const now = new Date(2026, 8, 29, 21, 30).getTime()
  expect(fmtMsgTime(new Date(2026, 8, 29, 9, 5).getTime(), 'de', now)).toBe('09:05')
  expect(fmtMsgTime(new Date(2026, 8, 28, 21, 14).getTime(), 'de', now)).toBe('28.09. 21:14')
  expect(fmtMsgTime(new Date(2025, 11, 24, 18, 0).getTime(), 'de', now)).toBe('24.12.25 18:00')
})
