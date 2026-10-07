import { describe, expect, it } from 'vitest'
import { aufgezogen, hoechstens, verschoben } from './blasenOrt'

describe('Sprechblase verschieben', () => {
  const gross = { w: 30, h: 40 }
  it('folgt der Maus: rechts = l größer, nach unten = b kleiner', () => {
    expect(verschoben({ l: 50, b: 40 }, 5, 10, gross)).toEqual({ l: 55, b: 30 })
  })
  it('bleibt ganz im Raum', () => {
    expect(verschoben({ l: 60, b: 50 }, 30, -30, gross)).toEqual({ l: 70, b: 60 })
    expect(verschoben({ l: 5, b: 5 }, -20, 20, gross)).toEqual({ l: 0, b: 0 })
  })
})

describe('Sprechblase aufziehen', () => {
  const min = { w: 15, h: 10 }
  const max = { w: 60, h: 80 }
  const start = { l: 20, b: 30, w: 30, h: 40 }
  it('oben rechts: nach rechts breiter, nach oben höher, unten links bleibt', () => {
    expect(aufgezogen(start, { x: 1, y: -1 }, 5, -10, min, max)).toEqual({ ...start, w: 35, h: 50 })
    expect(aufgezogen(start, { x: 1, y: -1 }, -5, 10, min, max)).toEqual({ ...start, w: 25, h: 30 })
  })
  it('links: die rechte Kante bleibt stehen', () => {
    expect(aufgezogen(start, { x: -1, y: 0 }, -5, 99, min, max)).toEqual({ ...start, l: 15, w: 35 })
  })
  it('unten: die obere Kante bleibt stehen', () => {
    expect(aufgezogen(start, { x: 0, y: 1 }, 99, 10, min, max)).toEqual({ ...start, b: 20, h: 50 })
  })
  it('Ecke unten links: beides', () => {
    expect(aufgezogen(start, { x: -1, y: 1 }, -5, 10, min, max)).toEqual({
      l: 15,
      b: 20,
      w: 35,
      h: 50,
    })
  })
  it('wird nicht kleiner als lesbar und nicht größer als der Platz', () => {
    expect(aufgezogen(start, { x: 1, y: -1 }, -50, 50, min, max)).toEqual({ ...start, ...min })
    // rechts bis 99, oben bis 98
    expect(aufgezogen(start, { x: 1, y: -1 }, 90, -90, min, max)).toEqual({
      ...start,
      w: 60,
      h: 68,
    })
    // links und unten bis an den Rand des Raums
    expect(aufgezogen(start, { x: -1, y: 1 }, -90, 90, min, max)).toEqual({
      l: 0,
      b: 0,
      w: 50,
      h: 70,
    })
  })
  it('ist kein Platz mehr da, gilt die Mindestgröße', () => {
    expect(aufgezogen(start, { x: 1, y: -1 }, 10, -10, min, { w: 5, h: 5 })).toEqual({
      ...start,
      ...min,
    })
  })
})

describe('Sprechblase bleibt im Raum', () => {
  it('wächst höchstens bis unter die Decke', () => {
    expect(hoechstens(43, 20)).toBe(43)
    expect(hoechstens(43, 70)).toBe(28)
  })
})
