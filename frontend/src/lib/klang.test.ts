import { bisVolleSekunde } from '@/hooks/useSekunde'
import {
  codyTippt,
  klangAktiv,
  klangEinstellen,
  naechsteSekundeAudio,
  oeffnen,
  pegel,
  tipp,
  uhr,
} from './klang'
import { SCHLAG, TAKT, takt, zufall } from './klangMusik'

describe('Musik', () => {
  it('bleibt im Takt und in vernünftigen Lagen', () => {
    const rnd = zufall(42)
    for (let nr = 0; nr < 64; nr++) {
      for (const e of takt(nr, rnd)) {
        expect(e.t).toBeGreaterThanOrEqual(0)
        expect(e.t).toBeLessThan(TAKT)
        expect(e.vel).toBeGreaterThan(0)
        expect(e.vel).toBeLessThanOrEqual(1)
        if (e.note !== undefined) {
          expect(e.note).toBeGreaterThanOrEqual(33)
          expect(e.note).toBeLessThanOrEqual(88)
        }
      }
    }
  })

  it('Snare auf 2 und 4, Kick auf der Eins', () => {
    const ev = takt(0, zufall(1))
    expect(ev.filter((e) => e.stimme === 'snare').map((e) => e.t)).toEqual([SCHLAG, 3 * SCHLAG])
    expect(ev.some((e) => e.stimme === 'kick' && e.t === 0)).toBe(true)
  })

  it('gleicher Startwert, gleiche Musik — anderer Startwert, andere', () => {
    const a = takt(5, zufall(7))
    expect(takt(5, zufall(7))).toEqual(a)
    const verschieden = [1, 2, 3, 4, 5].some(
      (s) => JSON.stringify(takt(5, zufall(100 + s))) !== JSON.stringify(a),
    )
    expect(verschieden).toBe(true)
  })

  it('Melodie bleibt spärlich und setzt am Anfang der Folge aus', () => {
    const rnd = zufall(3)
    let toene = 0
    for (let nr = 0; nr < 80; nr++) {
      const m = takt(nr, rnd).filter((e) => e.stimme === 'melodie')
      if (nr % 8 < 2) expect(m).toEqual([])
      toene += m.length
    }
    expect(toene / 80).toBeLessThan(3)
  })
})

describe('Klang', () => {
  it('Lautstärke wächst quadratisch und bleibt in 0–1', () => {
    expect(pegel(0)).toBe(0)
    expect(pegel(100)).toBe(1)
    expect(pegel(50)).toBeCloseTo(0.25)
    expect(pegel(250)).toBe(1)
    expect(pegel(-5)).toBe(0)
  })

  it('ohne Web Audio passiert einfach nichts', () => {
    expect(window.AudioContext).toBeUndefined()
    expect(() => {
      klangEinstellen({ effekte: true, musik: true, lautstaerke: 40 })
      klangAktiv(true)
      tipp()
      oeffnen()
      uhr(true)
      codyTippt(true)
      uhr(false)
      codyTippt(false)
      klangAktiv(false)
    }).not.toThrow()
  })
})

describe('Uhr im Takt', () => {
  it('Tick fällt auf die volle Sekunde, Latenz schon abgezogen', () => {
    // 300 ms vor der vollen Sekunde, Audio-Uhr bei 10 s, 40 ms Ausgabeverzögerung
    expect(naechsteSekundeAudio(10, 5_700, 0.04)).toBeCloseTo(10.26)
    expect(naechsteSekundeAudio(3, 1_000, 0)).toBeCloseTo(4)
  })

  it('Anzeige springt kurz nach der vollen Sekunde', () => {
    expect(bisVolleSekunde(12_345)).toBe(660)
    expect(bisVolleSekunde(13_000)).toBe(1005)
  })
})
