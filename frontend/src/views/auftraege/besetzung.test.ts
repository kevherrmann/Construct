import { besetzung } from './besetzung'
import type { Auftrag, Nachricht } from '@/api/team'

const auftrag = { owner: 'chef' } as Auftrag
const msg = (von: string, an: string, art: Nachricht['art'], id: string): Nachricht => ({
  id,
  ts: 0,
  von,
  an,
  art,
  text: '',
})

describe('besetzung', () => {
  it('hängt jeden an den, der ihn zuerst geholt hat', () => {
    const verlauf = [
      msg('kevin', 'chef', 'auftrag', 'm1'),
      msg('chef', 'dev', 'auftrag', 'm2'),
      msg('chef', 'qa', 'auftrag', 'm3'),
      msg('dev', 'qa', 'frage', 'm4'), // qa hängt trotzdem an chef: der hat zuerst gefragt
    ]
    const b = besetzung(auftrag, verlauf, '')
    expect(b.slug).toBe('chef')
    expect(b.kinder.map((k) => k.slug)).toEqual(['dev', 'qa'])
    expect(b.kinder.find((k) => k.slug === 'qa')!.kinder).toEqual([])
  })

  it('merkt, wer arbeitet, wer geliefert hat und wer noch stumm ist', () => {
    const verlauf = [
      msg('kevin', 'chef', 'auftrag', 'm1'),
      msg('chef', 'dev', 'auftrag', 'm2'),
      msg('dev', 'chef', 'ergebnis', 'm3'),
      msg('chef', 'qa', 'auftrag', 'm4'),
    ]
    const b = besetzung(auftrag, verlauf, 'qa')
    const dev = b.kinder.find((k) => k.slug === 'dev')!
    const qa = b.kinder.find((k) => k.slug === 'qa')!
    expect(dev.geliefert).toBe('chef')
    expect(dev.stumm).toBe(false)
    expect(qa.arbeitet).toBe(true)
    expect(qa.stumm).toBe(true)
  })

  it('kommt ohne Nachrichten aus: nur die Geschäftsführung', () => {
    const b = besetzung(auftrag, [], '')
    expect(b.slug).toBe('chef')
    expect(b.kinder).toEqual([])
  })
})
