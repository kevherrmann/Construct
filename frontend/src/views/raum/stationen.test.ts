import { describe, expect, it } from 'vitest'
import {
  BUERO_BUEHNE,
  DOPPEL,
  DOPPEL_HOEHE,
  FERNSEHER,
  FIGUR,
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

  it('die Doppeltische überlappen sich nicht und lassen die Figur auf dem Podest dazwischen', () => {
    const breite = (p: { s: number }) => ((DOPPEL.inhaltW * DOPPEL_HOEHE) / DOPPEL.inhaltH) * p.s
    const a = PAARE.a
    const b = PAARE.b
    expect(a.x + breite(a) / 2).toBeLessThan(b.x - breite(b) / 2)
    const figurX = (FIGUR.x / 100) * BUERO_BUEHNE.w
    expect(figurX).toBeGreaterThan(a.x)
    expect(figurX).toBeLessThan(b.x)
  })

  it('die Firma-Station liegt ganz unten im Stapel, damit Wandobjekte Vorrang haben', () => {
    expect(STATIONEN[0]?.id).toBe('firma')
  })

  it('die Klickform des Bildschirms ist sein Viereck im Rechteck der Station', () => {
    const st = STATIONEN.find((x) => x.id === 'monitore')!
    FERNSEHER.forEach(([x, y], i) => {
      const [fx, fy] = st.form![i]!
      expect(st.l + (fx / 100) * st.w).toBeCloseTo(x, 0)
      expect(st.t + (fy / 100) * st.h).toBeCloseTo(y, 0)
    })
  })

  it('der Bildschirm steht im Stapel über der Lochwand (Skills)', () => {
    const i = (id: string) => STATIONEN.findIndex((x) => x.id === id)
    expect(i('monitore')).toBeGreaterThan(i('werkzeug'))
  })
})
