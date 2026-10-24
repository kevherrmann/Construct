import { datum, tagsDazu, zeitpunkt } from './format'

it('datum: ISO wird deutsch, leer bleibt leer', () => {
  expect(datum('2023-01-23')).toBe('23.01.2023')
  expect(datum(null)).toBe('')
  expect(datum('kaputt')).toBe('')
})

it('tagsDazu: Komma trennt, Doppelte ohne Groß/klein fallen weg', () => {
  expect(tagsDazu(['Steuer'], 'steuer, Haus ,  Bahnhofstraße  76')).toEqual([
    'Steuer',
    'Haus',
    'Bahnhofstraße 76',
  ])
  expect(tagsDazu([], ' , ')).toEqual([])
})

it('zeitpunkt: Datum und Uhrzeit', () => {
  expect(zeitpunkt('2026-10-25T00:18:43')).toBe('25.10.2026 00:18')
  expect(zeitpunkt('')).toBe('')
})
