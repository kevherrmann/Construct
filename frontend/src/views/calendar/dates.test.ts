import type { CalEvent } from '@/api/calendar'
import {
  eventsOn,
  gridRange,
  monthGrid,
  monthName,
  occDate,
  occursOn,
  parseYMD,
  upcoming,
  weekdays,
  ymd,
} from './dates'

const ev = (p: Partial<CalEvent>): CalEvent => ({
  id: p.id ?? Math.random().toString(36).slice(2),
  date: '2026-09-25',
  time: '',
  title: 'x',
  notes: '',
  repeat: '',
  prompt: '',
  created: '',
  ...p,
})

describe('monthGrid', () => {
  it('beginnt am Montag vor dem 1. und hat immer 42 Tage', () => {
    // 1. September 2026 ist ein Dienstag
    const g = monthGrid(2026, 8)
    expect(g).toHaveLength(42)
    expect(g[0]).toEqual({ ds: '2026-08-31', day: 31, other: true })
    expect(g[1]).toEqual({ ds: '2026-09-01', day: 1, other: false })
    expect(g[41]).toEqual({ ds: '2026-10-11', day: 11, other: true })
  })

  it('fängt direkt am 1. an, wenn der ein Montag ist', () => {
    // 1. Juni 2026 ist ein Montag
    expect(monthGrid(2026, 5)[0]!.ds).toBe('2026-06-01')
  })

  it('stolpert nicht über die Zeitumstellung', () => {
    // Ende März / Oktober: jede Zelle ein anderer, lückenloser Tag
    for (const m of [2, 9]) {
      const days = monthGrid(2026, m).map((d) => d.ds)
      expect(new Set(days).size).toBe(42)
      for (let i = 1; i < 42; i++) {
        const diff = parseYMD(days[i]!).getTime() - parseYMD(days[i - 1]!).getTime()
        expect(Math.round(diff / 864e5)).toBe(1)
      }
    }
  })

  it('liefert den Bereich für /api/activity', () => {
    expect(gridRange(2026, 8)).toEqual(['2026-08-31', '2026-10-11'])
    // Jahreswechsel
    expect(gridRange(2027, 0)).toEqual(['2026-12-28', '2027-02-07'])
  })
})

describe('Wiederholung', () => {
  const bday = ev({ date: '1985-10-03', repeat: 'yearly' })

  it('jährliche Termine gelten jedes Jahr am selben Tag', () => {
    expect(occursOn(bday, '2026-10-03')).toBe(true)
    expect(occursOn(bday, '1985-10-03')).toBe(true)
    expect(occursOn(bday, '2026-10-04')).toBe(false)
  })

  it('einmalige nur am eigenen Datum', () => {
    const once = ev({ date: '2026-10-03' })
    expect(occursOn(once, '2026-10-03')).toBe(true)
    expect(occursOn(once, '2027-10-03')).toBe(false)
  })

  it('rollt das nächste Vorkommen ins Folgejahr, wenn es schon vorbei ist', () => {
    expect(occDate(bday, '2026-09-25')).toBe('2026-10-03')
    expect(occDate(bday, '2026-10-03')).toBe('2026-10-03')
    expect(occDate(bday, '2026-10-04')).toBe('2027-10-03')
    expect(occDate(ev({ date: '2020-01-01' }), '2026-09-25')).toBe('2020-01-01')
  })
})

describe('eventsOn / upcoming', () => {
  const events = [
    ev({ id: 'allday', date: '2026-09-25' }),
    ev({ id: 'late', date: '2026-09-25', time: '18:00' }),
    ev({ id: 'early', date: '2026-09-25', time: '09:30' }),
    ev({ id: 'past', date: '2026-09-01' }),
    ev({ id: 'bday', date: '1985-09-26', repeat: 'yearly' }),
    ev({ id: 'bdayPast', date: '1990-02-01', repeat: 'yearly' }),
  ]

  it('sortiert nach Uhrzeit, ganztägige vorn (wie bisher)', () => {
    expect(eventsOn(events, '2026-09-25').map((e) => e.id)).toEqual(['allday', 'early', 'late'])
  })

  it('zeigt nur Kommendes, chronologisch, jährliche mit nächstem Datum', () => {
    const up = upcoming(events, '2026-09-25')
    expect(up.map((x) => [x.e.id, x.d])).toEqual([
      ['allday', '2026-09-25'],
      ['early', '2026-09-25'],
      ['late', '2026-09-25'],
      ['bday', '2026-09-26'],
      ['bdayPast', '2027-02-01'],
    ])
    expect(upcoming(events, '2026-09-25', 2)).toHaveLength(2)
  })
})

it('Namen passen zur Sprache', () => {
  expect(monthName('de', 2)).toBe('März')
  expect(monthName('en', 2)).toBe('March')
  expect(weekdays('de')[0]).toBe('Mo')
  expect(weekdays('en')[6]).toBe('Sun')
  expect(ymd(2026, 0, 5)).toBe('2026-01-05')
})
