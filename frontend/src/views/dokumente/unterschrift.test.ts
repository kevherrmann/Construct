import { describe, expect, it, beforeEach } from 'vitest'
import type { Element } from '@/api/dokumente'
import { heute, ortDatum, ortHolen, ortMerken, vergroessert, verschoben } from './unterschrift'

const A4 = { breite: 595, hoehe: 842 }

describe('unterschrift', () => {
  beforeEach(() => localStorage.clear())

  it('Ort vom letzten Mal, Datum von heute', () => {
    const d = new Date(2026, 10, 5)
    expect(heute(d)).toBe('05.11.2026')
    expect(ortDatum(null, d)).toBe('05.11.2026')
    ortMerken([{ art: 'text', seite: 1, x: 0, y: 0, hoehe: 0.02, text: 'Lengerich, 01.02.2026' }])
    expect(ortHolen()).toBe('Lengerich')
    expect(ortDatum(ortHolen(), d)).toBe('Lengerich, 05.11.2026')
  })

  it('merkt sich keinen Ort aus beliebigem Text', () => {
    ortMerken([
      { art: 'text', seite: 1, x: 0, y: 0, hoehe: 0.02, text: 'Gelesen und einverstanden' },
    ])
    expect(ortHolen()).toBeNull()
  })

  it('bleibt beim Verschieben greifbar auf der Seite', () => {
    const e: Element = { art: 'unterschrift', seite: 1, x: 0.5, y: 0.5, breite: 0.3 }
    expect(verschoben(e, 2, -2)).toMatchObject({ x: 0.97, y: -0.02 })
  })

  it('Größe hat Grenzen', () => {
    const sig: Element = { art: 'unterschrift', seite: 1, x: 0, y: 0, breite: 0.3 }
    expect(vergroessert(sig, -1, A4)).toMatchObject({ breite: 0.05 })
    const txt: Element = { art: 'text', seite: 1, x: 0, y: 0, hoehe: 11 / 842, text: 'abc' }
    expect(vergroessert(txt, 5, A4).art === 'text' && vergroessert(txt, 5, A4)).toMatchObject({
      hoehe: 40 / 842,
    })
  })
})
