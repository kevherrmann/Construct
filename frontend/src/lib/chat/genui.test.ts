import { describe, expect, it } from 'vitest'
import { ohneUi, parseSpec, splitUi } from './genui'

const block = (json: string) => '```ui\n' + json + '\n```'

describe('parseSpec', () => {
  it('liest Antwort-Buttons', () => {
    expect(parseSpec('{"type":"choices","question":"Welche?","options":["A","B"]}')).toEqual({
      type: 'choices',
      question: 'Welche?',
      options: ['A', 'B'],
    })
  })

  it('nimmt auch Objekte mit label und wirft Doppelte und Leere raus', () => {
    const s = parseSpec('{"type":"choices","options":[{"label":"Ja"},"Ja"," ",{"x":1},"Nein"]}')
    expect(s).toEqual({ type: 'choices', question: '', options: ['Ja', 'Nein'] })
  })

  it('verwirft Buttons ohne Optionen', () => {
    expect(parseSpec('{"type":"choices","options":[]}')).toBeNull()
    expect(parseSpec('{"type":"choices"}')).toBeNull()
  })

  it('liest einen Termin und ergänzt die führende Null der Uhrzeit', () => {
    expect(
      parseSpec('{"type":"event","title":"Zahnarzt","date":"2026-11-03","time":"9:30"}'),
    ).toEqual({ type: 'event', title: 'Zahnarzt', date: '2026-11-03', time: '09:30', notes: '' })
  })

  it('verwirft Termine mit falschem Datum oder falscher Uhrzeit', () => {
    expect(parseSpec('{"type":"event","title":"X","date":"2026-02-30"}')).toBeNull()
    expect(parseSpec('{"type":"event","title":"X","date":"3.11.2026"}')).toBeNull()
    expect(parseSpec('{"type":"event","title":"X","date":"2026-11-03","time":"25:00"}')).toBeNull()
    expect(parseSpec('{"type":"event","date":"2026-11-03"}')).toBeNull()
  })

  it('verwirft kaputtes JSON und unbekannte Typen', () => {
    expect(parseSpec('{"type":"choices",')).toBeNull()
    expect(parseSpec('{"type":"chart"}')).toBeNull()
    expect(parseSpec('[1,2]')).toBeNull()
  })
})

describe('splitUi', () => {
  it('lässt Text ohne Baustein unverändert', () => {
    expect(splitUi('Hallo **du**')).toEqual([{ t: 'md', text: 'Hallo **du**' }])
  })

  it('zerlegt Text und Baustein', () => {
    const text = `Was darf es sein?\n\n${block('{"type":"choices","options":["A","B"]}')}\n\nDanach.`
    expect(splitUi(text)).toEqual([
      { t: 'md', text: 'Was darf es sein?\n' },
      { t: 'ui', spec: { type: 'choices', question: '', options: ['A', 'B'] } },
      { t: 'md', text: '\nDanach.' },
    ])
  })

  it('macht aus kaputtem JSON einen gewöhnlichen Codeblock', () => {
    const parts = splitUi(block('{"type":"choices",'))
    expect(parts).toEqual([{ t: 'md', text: '```json\n{"type":"choices",\n```' }])
  })

  it('zeigt einen offenen Block beim Streamen als Platzhalter', () => {
    expect(splitUi('Moment:\n```ui\n{"type":"cho', true)).toEqual([
      { t: 'md', text: 'Moment:' },
      { t: 'pending' },
    ])
  })

  it('ein nach dem Streamen offener Block bleibt als Code sichtbar', () => {
    const parts = splitUi('```ui\n{"type":"cho')
    expect(parts).toEqual([{ t: 'md', text: '```json\n{"type":"cho\n```' }])
  })

  it('übergeht ```ui als Beispiel in einem anderen Codeblock', () => {
    const text = '````markdown\n```ui\n{"type":"choices","options":["A"]}\n```\n````'
    expect(splitUi(text)).toEqual([{ t: 'md', text }])
  })
})

describe('ohneUi', () => {
  it('entfernt Bausteine fürs Vorlesen', () => {
    const text = `Termin?\n${block('{"type":"event","title":"X","date":"2026-11-03"}')}`
    expect(ohneUi(text).trim()).toBe('Termin?')
  })
})
