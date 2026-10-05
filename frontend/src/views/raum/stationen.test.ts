import { describe, expect, it } from 'vitest'
import { BUERO_BUEHNE, PLAETZE, STATIONEN, WERKBANK_FUSS } from './stationen'

describe('Büro im Raum', () => {
  it('alle Schreibtische liegen auf der Bühne und keine zwei übereinander', () => {
    for (const p of PLAETZE) {
      expect(p.x).toBeGreaterThan(0)
      expect(p.x).toBeLessThan(BUERO_BUEHNE.w)
      expect(p.y).toBeGreaterThan(0)
      expect(p.y).toBeLessThan(BUERO_BUEHNE.h)
    }
    const ort = new Set(PLAETZE.map((p) => `${p.x},${p.y}`))
    expect(ort.size).toBe(PLAETZE.length)
  })

  it('die Werkbank ist vom Büro aus erreichbar (steht vor den Tischen)', () => {
    expect(PLAETZE.every((p) => p.y < WERKBANK_FUSS.y)).toBe(true)
  })

  it('die Firma-Station liegt ganz unten im Stapel, damit Tische und Wandobjekte Vorrang haben', () => {
    expect(STATIONEN[0]?.id).toBe('firma')
  })
})
