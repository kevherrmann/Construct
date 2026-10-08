import { describe, expect, it } from 'vitest'
import type { Helfer } from '@/lib/chat/types'
import {
  ERSCHEINEN_MS,
  FLACKERN_MS,
  PLAETZE,
  ZERFALL_MS,
  aufstellung,
  holosNach,
  naechsteAenderung,
  nebenMitarbeiter,
  ortVon,
  wartende,
  type Holo,
} from './hologramme'
import { WERKBANK } from './stationen'

const helfer = (id: string, x: Partial<Helfer> = {}): Helfer => ({
  id,
  antwort: 'b1',
  beschreibung: `Helfer ${id}`,
  typ: 'general-purpose',
  stand: 'start',
  werkzeug: '',
  detail: '',
  hintergrund: false,
  ...x,
})

/** Mehrere Schritte nacheinander, jeweils mit Zeitpunkt. */
const ablauf = (schritte: [number, Helfer[]][]) =>
  schritte.reduce<Holo[]>((v, [t, h]) => holosNach(v, h, t), [])

describe('holosNach', () => {
  it('ein neuer Helfer erscheint neben der Figur, auf dem ersten Platz', () => {
    const [h] = holosNach([], [helfer('a', { werkzeug: 'Read' })], 1000)
    expect(h).toMatchObject({ id: 'a', phase: 'erscheint', seit: 1000, platz: 0, ort: 'neben' })
  })

  it('geht erst nach dem Aufbau an die Station seines Werkzeugs', () => {
    const liste = [helfer('a', { stand: 'laeuft', werkzeug: 'Read', detail: 'Reading eins.txt' })]
    const kurz = ablauf([
      [0, liste],
      [ERSCHEINEN_MS - 1, liste],
    ])
    expect(kurz[0]).toMatchObject({ phase: 'erscheint', ort: 'neben' })
    const da = ablauf([
      [0, liste],
      [ERSCHEINEN_MS, liste],
    ])
    expect(da[0]).toMatchObject({ phase: 'arbeitet', ort: 'regal', detail: 'Reading eins.txt' })
  })

  it('wechselt mit dem Werkzeug die Station', () => {
    const v = ablauf([
      [0, [helfer('a', { werkzeug: 'Read' })]],
      [900, [helfer('a', { werkzeug: 'Read' })]],
      [1200, [helfer('a', { stand: 'laeuft', werkzeug: 'Edit' })]],
    ])
    expect(v[0]!.ort).toBe('werkbank')
  })

  it('ändert sich nichts, kommt dieselbe Liste zurück', () => {
    const v = holosNach([], [helfer('a')], 0)
    expect(holosNach(v, [helfer('a')], 10)).toBe(v)
    expect(holosNach([], [], 0)).toEqual([])
  })

  it('fertig: zerfällt am Ort, an dem es stand, und ist danach weg', () => {
    const v = ablauf([
      [0, [helfer('a', { werkzeug: 'Bash' })]],
      [900, [helfer('a', { werkzeug: 'Bash' })]],
      [2000, [helfer('a', { stand: 'fertig', werkzeug: 'Bash' })]],
    ])
    expect(v[0]).toMatchObject({ phase: 'zerfaellt', seit: 2000, ort: 'werkbank' })
    expect(holosNach(v, [], 2000 + ZERFALL_MS - 1)).toHaveLength(1)
    expect(holosNach(v, [], 2000 + ZERFALL_MS)).toEqual([])
  })

  it('verschwindet die Liste (Lauf zu Ende), zerfallen die offenen trotzdem', () => {
    const v = ablauf([
      [0, [helfer('a')]],
      [500, []],
    ])
    expect(v[0]).toMatchObject({ phase: 'zerfaellt', seit: 500 })
  })

  it('Fehler: flackert aus', () => {
    const v = ablauf([
      [0, [helfer('a')]],
      [300, [helfer('a', { stand: 'fehler' })]],
    ])
    expect(v[0]).toMatchObject({ phase: 'flackert', seit: 300 })
    expect(holosNach(v, [], 300 + FLACKERN_MS)).toEqual([])
  })

  it('ein Helfer, der schon fertig ist, erscheint nicht erst', () => {
    expect(holosNach([], [helfer('a', { stand: 'fertig' })], 0)).toEqual([])
  })

  it('ab dem fünften warten sie auf einen Platz und rücken nach', () => {
    const fuenf = ['a', 'b', 'c', 'd', 'e'].map((id) => helfer(id))
    let v = holosNach([], fuenf, 0)
    expect(v.map((h) => h.platz)).toEqual([0, 1, 2, 3, -1])
    expect(wartende(v)).toBe(1)
    expect(PLAETZE).toBe(4)
    // b ist fertig: zerfällt, behält seinen Platz bis zum Ende
    const ohneB = fuenf.map((h) => (h.id === 'b' ? { ...h, stand: 'fertig' as const } : h))
    v = holosNach(v, ohneB, 100)
    expect(v.find((h) => h.id === 'e')!.platz).toBe(-1)
    // danach rückt e auf Platz 1 und erscheint frisch
    v = holosNach(v, ohneB, 100 + ZERFALL_MS)
    expect(v.find((h) => h.id === 'e')).toMatchObject({
      platz: 1,
      phase: 'erscheint',
      seit: 100 + ZERFALL_MS,
    })
    expect(v.some((h) => h.id === 'b')).toBe(false)
  })

  it('ein wartender, der fertig wird, verschwindet ohne Zerfall', () => {
    const fuenf = ['a', 'b', 'c', 'd', 'e'].map((id) => helfer(id))
    const v = holosNach([], fuenf, 0)
    const n = holosNach(v, [...fuenf.slice(0, 4), helfer('e', { stand: 'fertig' })], 10)
    expect(n.some((h) => h.id === 'e')).toBe(false)
  })
})

describe('naechsteAenderung', () => {
  it('wartet bis zum Ende der laufenden Phase', () => {
    const v = holosNach([], [helfer('a')], 0)
    expect(naechsteAenderung(v, 300)).toBe(ERSCHEINEN_MS - 300)
    const da = holosNach(v, [helfer('a')], ERSCHEINEN_MS)
    expect(naechsteAenderung(da, ERSCHEINEN_MS)).toBeNull()
  })
})

describe('ortVon', () => {
  it('ordnet Werkzeuge wie die Figur zu', () => {
    expect(ortVon('Read')).toBe('regal')
    expect(ortVon('Grep')).toBe('regal')
    expect(ortVon('Write')).toBe('werkbank')
    expect(ortVon('Bash')).toBe('werkbank')
    expect(ortVon('WebSearch')).toBe('werkbank')
    expect(ortVon('Agent')).toBe('neben')
    expect(ortVon('')).toBe('neben')
  })
})

describe('aufstellung', () => {
  const da = (id: string, platz: number, ort: Holo['ort']): Holo => ({
    id,
    beschreibung: '',
    detail: '',
    werkzeug: '',
    phase: 'arbeitet',
    seit: 0,
    platz,
    ort,
  })

  it('neben dem Podest stehen alle an verschiedenen Stellen', () => {
    const st = aufstellung(
      [0, 1, 2, 3].map((i) => da(`h${i}`, i, 'neben')),
      true,
    )
    const punkte = [...st.values()].map((s) => (s.art === 'pose' ? `${s.x},${s.y}` : ''))
    expect(new Set(punkte).size).toBe(4)
  })

  it('an der freien Werkbank tippt der erste am Platz der Figur', () => {
    const st = aufstellung([da('a', 0, 'werkbank'), da('b', 1, 'werkbank')], true)
    expect(st.get('a')).toEqual({ art: 'werkbank', r: WERKBANK })
    expect(st.get('b')).toMatchObject({ art: 'werkbank' })
    expect(st.get('b')).not.toEqual(st.get('a'))
  })

  it('ist die Werkbank besetzt, weicht er aus', () => {
    const st = aufstellung([da('a', 0, 'werkbank')], false)
    expect(st.get('a')).not.toEqual({ art: 'werkbank', r: WERKBANK })
  })

  it('wartende stehen nirgends', () => {
    expect(aufstellung([da('a', -1, 'neben')], true).size).toBe(0)
  })
})

describe('nebenMitarbeiter', () => {
  const platz = { x: 700, y: 340, s: 1.2 }
  it('am Doppeltisch außen daneben, nie über dem Tisch', () => {
    const links = nebenMitarbeiter(false, { platz, paar: 'a' }, 0)
    const rechts = nebenMitarbeiter(false, { platz, paar: 'b' }, 0)
    const mitte = (r: { l: number; w: number }) => r.l + r.w * (350 / 768)
    expect(mitte(links)).toBeLessThan(30)
    expect(mitte(rechts)).toBeGreaterThan(70)
  })
  it('an der Werkbank: der erste tippt neben ihm, weitere stehen woanders', () => {
    const a = nebenMitarbeiter(true, { platz }, 0)
    const b = nebenMitarbeiter(true, { platz }, 1)
    expect(a.l).toBeGreaterThan(WERKBANK.l)
    expect(b.l).toBeLessThan(WERKBANK.l)
  })
})
