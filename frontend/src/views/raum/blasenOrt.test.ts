import { describe, expect, it } from 'vitest'
import { verschoben } from './blasenOrt'

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
