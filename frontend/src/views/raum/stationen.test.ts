import { describe, expect, it } from 'vitest'
import {
  BUERO_BUEHNE,
  PAARE,
  RANDPLAETZE,
  SITZE,
  STATIONEN,
  WERKBANK_FUSS,
  sitzFuss,
} from './stationen'

describe('Büro im Raum', () => {
  it('alle Tische und Sitze liegen auf der Bühne', () => {
    for (const p of Object.values(PAARE)) {
      expect(p.x).toBeGreaterThan(0)
      expect(p.x).toBeLessThan(BUERO_BUEHNE.w)
      expect(p.y).toBeGreaterThan(0)
      expect(p.y).toBeLessThan(BUERO_BUEHNE.h)
    }
    for (const { paar, seite } of Object.values(SITZE)) {
      const f = sitzFuss(paar, seite)
      expect(f.x).toBeGreaterThan(0)
      expect(f.x).toBeLessThan(BUERO_BUEHNE.w)
    }
    for (const p of RANDPLAETZE) expect(p.x).toBeGreaterThan(0)
  })

  it('jeder Sitz gehört genau einer Person, links und rechts je Tisch', () => {
    const belegt = Object.values(SITZE).map((x) => `${x.paar}-${x.seite}`)
    expect(new Set(belegt).size).toBe(belegt.length)
    expect(sitzFuss('a', 'links').x).toBeLessThan(sitzFuss('a', 'rechts').x)
  })

  it('die Werkbank liegt vor den Tischen (näher am Betrachter)', () => {
    for (const p of Object.values(PAARE)) expect(p.y).toBeLessThan(WERKBANK_FUSS.y)
  })

  it('die Tische stehen nicht vor dem Fernseher (links von dessen Kante)', () => {
    // Der Fernseher beginnt bei etwa 47 % der Bühne.
    for (const p of Object.values(PAARE)) expect(p.x / BUERO_BUEHNE.w).toBeLessThan(0.42)
  })

  it('die Firma-Station liegt ganz unten im Stapel, damit Wandobjekte Vorrang haben', () => {
    expect(STATIONEN[0]?.id).toBe('firma')
  })
})
