import { describe, expect, it } from 'vitest'
import { vergroessert, verschoben } from './blasenOrt'

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
  it('Griff oben rechts: nach rechts breiter, nach oben höher', () => {
    expect(vergroessert({ w: 30, h: 40 }, 5, -10, min, max)).toEqual({ w: 35, h: 50 })
    expect(vergroessert({ w: 30, h: 40 }, -5, 10, min, max)).toEqual({ w: 25, h: 30 })
  })
  it('wird nicht kleiner als lesbar und nicht größer als der Platz', () => {
    expect(vergroessert({ w: 30, h: 40 }, -50, 50, min, max)).toEqual(min)
    expect(vergroessert({ w: 30, h: 40 }, 90, -90, min, max)).toEqual(max)
  })
  it('ist kein Platz mehr da, gilt die Mindestgröße', () => {
    expect(vergroessert({ w: 30, h: 40 }, 10, -10, min, { w: 5, h: 5 })).toEqual(min)
  })
})
