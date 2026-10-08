import { describe, expect, it } from 'vitest'
import { helferNach, helferOffen } from './helfer'
import { applyEvent, initialRun, type RunState } from './reducer'
import type { StreamEvent } from './types'

const run = (events: StreamEvent[]): RunState => events.reduce(applyEvent, initialRun())
const AGENT = 'toolu_0132jWkGJw8rVyPgopMoXXKu'

// So schickt der Server einen Helfer (aus einem echten Lauf, 08.10.2026).
const START: StreamEvent = {
  type: 'helfer',
  id: AGENT,
  stand: 'start',
  beschreibung: 'Datei eins.txt lesen',
  typ: 'Explore',
  hintergrund: false,
}
const LAEUFT: StreamEvent = {
  type: 'helfer',
  id: AGENT,
  stand: 'laeuft',
  detail: 'Reading eins.txt',
  werkzeug: 'Read',
}
const AUFRUF: StreamEvent = {
  type: 'tool',
  id: AGENT,
  name: 'Agent',
  input: { description: 'Datei eins.txt lesen' },
}
const LESEN: StreamEvent = {
  type: 'tool',
  id: 'toolu_read',
  name: 'Read',
  input: { file_path: '/tmp/eins.txt' },
  parent: AGENT,
}

describe('Helfer', () => {
  it('erscheint mit dem Start an der laufenden Antwort', () => {
    const s = run([AUFRUF, START])
    expect(s.helfer).toEqual([
      {
        id: AGENT,
        antwort: s.items[0]!.id,
        beschreibung: 'Datei eins.txt lesen',
        typ: 'Explore',
        stand: 'start',
        werkzeug: '',
        detail: '',
        hintergrund: false,
      },
    ])
  })

  it('arbeitet mit dem Werkzeug aus Fortschritt oder eigenem Schritt und wird fertig', () => {
    const s = run([AUFRUF, START, LESEN])
    expect(s.helfer[0]).toMatchObject({ stand: 'laeuft', werkzeug: 'Read', detail: '' })
    const t = run([AUFRUF, START, LAEUFT, LESEN])
    expect(t.helfer[0]).toMatchObject({ werkzeug: 'Read', detail: 'Reading eins.txt' })
    const f = run([AUFRUF, START, LAEUFT, { type: 'helfer', id: AGENT, stand: 'fertig' }])
    // Beim Ende bleibt, was er zuletzt tat: der Raum lässt es dort zerfallen.
    expect(f.helfer[0]).toMatchObject({ stand: 'fertig', werkzeug: 'Read' })
  })

  it('markiert die Schritte des Helfers in der Antwort, ohne den Chat zu ändern', () => {
    const s = run([AUFRUF, START, LESEN])
    const antwort = s.items[0]!
    const tools = antwort.kind === 'bot' ? antwort.blocks : []
    expect(tools.map((b) => (b.t === 'tool' ? [b.name, b.parent] : b.t))).toEqual([
      ['Agent', undefined],
      ['Read', AGENT],
    ])
  })

  it('wird beim Replay nicht doppelt und ein Ende ohne Start erzeugt keinen', () => {
    expect(run([START, START]).helfer).toHaveLength(1)
    expect(run([{ type: 'helfer', id: 'x', stand: 'fertig' }]).helfer).toEqual([])
    expect(run([LESEN]).helfer).toEqual([])
  })

  it('ein beendeter Helfer lebt nicht wieder auf', () => {
    const s = run([START, { type: 'helfer', id: AGENT, stand: 'fehler' }, LAEUFT, LESEN])
    expect(s.helfer[0]!.stand).toBe('fehler')
  })

  it('mehrere parallel bleiben in der Reihenfolge ihres Starts', () => {
    const zweiter: StreamEvent = { ...START, id: 'toolu_2', beschreibung: 'Zweiter' }
    const s = run([START, zweiter, { type: 'helfer', id: AGENT, stand: 'fertig' }])
    expect(s.helfer.map((h) => [h.id, h.stand])).toEqual([
      [AGENT, 'fertig'],
      ['toolu_2', 'start'],
    ])
  })

  it('bleibt nach dem Ende des Laufs nie offen hängen', () => {
    // done ohne Ende-Meldung (etwa ein nach Neustart nachgelesener Lauf)
    expect(run([START, LAEUFT, { type: 'done' }]).helfer[0]!.stand).toBe('fertig')
    expect(run([START, { type: 'closed' }]).helfer[0]!.stand).toBe('fertig')
    expect(run([START, { type: 'error', message: '⏹ Gestoppt.' }]).helfer[0]!.stand).toBe('fehler')
  })

  it('im Hintergrund überlebt er das Zugende im Nachlauf, nicht dessen Ende', () => {
    const hinten: StreamEvent = { ...START, id: 'toolu_bg', hintergrund: true }
    const s = run([START, hinten, { type: 'nachlauf', tasks: ['x'] }, { type: 'done' }])
    expect(s.helfer.map((h) => h.stand)).toEqual(['fertig', 'start'])
    expect(s.nachlauf).toBe(true)
    // Der Helfer meldet sich im Nachlauf: neue Sprechblase, er bleibt an der alten
    const t = run([
      hinten,
      { type: 'nachlauf' },
      { type: 'done' },
      { type: 'neuer_zug' },
      { ...LESEN, parent: 'toolu_bg' },
    ])
    expect(t.helfer[0]).toMatchObject({ stand: 'laeuft', antwort: t.items[0]!.id })
    expect(run([hinten, { type: 'nachlauf' }, { type: 'nachlauf_ende' }]).helfer[0]!.stand).toBe(
      'fertig',
    )
    // Ohne Nachlauf (Züge der Firma) stirbt er mit dem Prozess
    expect(run([hinten, { type: 'done' }]).helfer[0]!.stand).toBe('fertig')
  })

  it('gibt dieselbe Liste zurück, wenn sich nichts ändert', () => {
    const liste = run([START]).helfer
    const u = { antwort: 'b', nachlauf: false }
    expect(helferNach(liste, { type: 'text', text: 'x' }, u)).toBe(liste)
    expect(helferNach(liste, START, u)).toBe(liste)
    expect(helferOffen(liste[0]!)).toBe(true)
  })
})
