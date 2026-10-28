import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { formText, formWerte, ohneUi, parseSpec, splitUi, type UiSpec } from './genui'

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

describe('Formular', () => {
  const spec = parseSpec(
    JSON.stringify({
      type: 'form',
      title: 'Neuer Kunde',
      fields: [
        { label: 'Firma', required: true },
        { name: 'frist', label: 'Frist', type: 'date' },
        { label: 'Priorität', type: 'select', options: ['hoch', 'normal'] },
        { label: 'Leer', type: 'select' },
        { label: 'Notiz', type: 'textarea' },
        { label: 'Firma' },
        { type: 'text' },
      ],
    }),
  ) as Extract<UiSpec, { type: 'form' }>

  it('liest Felder, macht leere Auswahl zum Textfeld und wirft Doppelte raus', () => {
    expect(spec.fields.map((f) => [f.name, f.kind])).toEqual([
      ['Firma', 'text'],
      ['frist', 'date'],
      ['Priorität', 'select'],
      ['Leer', 'text'],
      ['Notiz', 'textarea'],
    ])
    expect(spec.fields[0]?.required).toBe(true)
  })

  it('verwirft Formulare ohne Felder', () => {
    expect(parseSpec('{"type":"form","fields":[]}')).toBeNull()
    expect(parseSpec('{"type":"form"}')).toBeNull()
  })

  it('macht aus den Werten eine Nachricht und liest sie wieder zurück', () => {
    const werte = { Firma: 'Müller GmbH', frist: '2026-11-05', Notiz: 'Zeile 1\nZeile 2' }
    const text = formText(spec, werte)
    expect(text).toBe(
      '**Neuer Kunde**\nFirma: Müller GmbH\nFrist: 2026-11-05\nNotiz: Zeile 1 / Zeile 2',
    )
    expect(formWerte(spec, text)).toEqual({
      Firma: 'Müller GmbH',
      frist: '2026-11-05',
      Notiz: 'Zeile 1 / Zeile 2',
    })
  })
})

describe('Diagramm', () => {
  it('liest Reihen und füllt fehlende Werte mit null', () => {
    const s = parseSpec(
      JSON.stringify({
        type: 'chart',
        kind: 'line',
        labels: ['KW40', 'KW41', 'KW42'],
        series: [
          { name: 'Neu', values: [3, '5'] },
          { name: 'Leer', values: [] },
        ],
      }),
    )
    expect(s).toEqual({
      type: 'chart',
      kind: 'line',
      title: '',
      unit: '',
      labels: ['KW40', 'KW41', 'KW42'],
      series: [{ name: 'Neu', values: [3, 5, null] }],
    })
  })

  it('nimmt eine einzelne Reihe auch als values und kappt bei vier Reihen', () => {
    const eine = parseSpec('{"type":"chart","title":"Umsatz","labels":["A"],"values":[7]}')
    expect(eine).toMatchObject({ kind: 'bar', series: [{ name: 'Umsatz', values: [7] }] })
    const viele = parseSpec(
      JSON.stringify({
        type: 'chart',
        labels: ['A'],
        series: [1, 2, 3, 4, 5].map((v) => ({ name: `R${v}`, values: [v] })),
      }),
    ) as Extract<UiSpec, { type: 'chart' }>
    expect(viele.series.map((r) => r.name)).toEqual(['R1', 'R2', 'R3', 'R4'])
  })

  it('verwirft Diagramme ohne Beschriftung oder ohne Zahlen', () => {
    expect(parseSpec('{"type":"chart","labels":[],"values":[]}')).toBeNull()
    expect(parseSpec('{"type":"chart","labels":["A"],"values":["x"]}')).toBeNull()
  })
})

describe('Checkliste', () => {
  it('nimmt Texte und Objekte, done:true zählt als erledigt', () => {
    expect(
      parseSpec(
        JSON.stringify({
          type: 'checklist',
          title: 'Test',
          items: [
            'Anlegen',
            { text: 'Schalten', done: true },
            { text: 'Mail', state: 'failed' },
            3,
          ],
        }),
      ),
    ).toEqual({
      type: 'checklist',
      title: 'Test',
      items: [
        { text: 'Anlegen', state: 'open' },
        { text: 'Schalten', state: 'done' },
        { text: 'Mail', state: 'failed' },
      ],
    })
    expect(parseSpec('{"type":"checklist","items":[]}')).toBeNull()
  })
})

it('jedes Beispiel aus der Anleitung fürs Modell lässt sich lesen', () => {
  // server/genui.py ist, was die Modelle nachmachen. Liest der Parser dort ein
  // Beispiel nicht, stünde jeder so geschriebene Baustein als Code im Chat.
  const py = readFileSync(resolve(process.cwd(), '../server/genui.py'), 'utf-8')
  const beispiele = [...py.matchAll(/```ui\n(.*?)\n```/gs)].map((m) => m[1] ?? '')
  expect(beispiele).toHaveLength(10)
  for (const b of beispiele) expect(parseSpec(b), b).not.toBeNull()
})
