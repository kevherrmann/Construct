import { applyEvent, initialRun, type RunState } from './reducer'
import type { BotItem, StreamEvent } from './types'
import { SseParser } from './sse'

const run = (events: StreamEvent[]): RunState => events.reduce(applyEvent, initialRun())
const bots = (s: RunState) => s.items.filter((i): i is BotItem => i.kind === 'bot')

describe('applyEvent', () => {
  it('sammelt Text-Deltas in einem Block und schließt ihn bei done', () => {
    const s = run([
      { type: 'text', text: 'Hal' },
      { type: 'text', text: 'lo' },
    ])
    expect(bots(s)[0]!.thinking).toBe(false)
    expect(bots(s)[0]!.blocks).toEqual([{ t: 'text', text: 'Hallo', streaming: true }])
    const done = applyEvent(s, { type: 'done' })
    expect(bots(done)[0]!.blocks[0]).toEqual({ t: 'text', text: 'Hallo', streaming: false })
  })

  it('beginnt nach einem Werkzeug einen neuen Text-Block', () => {
    const s = run([
      { type: 'text', text: 'Ich schaue nach.' },
      { type: 'tool', id: 't1', name: 'Read', input: { file_path: '/a.txt' } },
      { type: 'tool_result', id: 't1', content: 'Inhalt' },
      { type: 'text', text: 'Fertig.' },
    ])
    const b = bots(s)[0]!.blocks
    expect(b.map((x) => x.t)).toEqual(['text', 'tool', 'text'])
    expect(b[0]).toMatchObject({ streaming: false })
    expect(b[1]).toMatchObject({ result: { content: 'Inhalt', isError: false } })
  })

  it('listet erfolgreich geschriebene Dateien nach der Statistik', () => {
    const s = run([
      { type: 'tool', id: 'w1', name: 'Write', input: { file_path: '/x/a.md', content: 'x' } },
      { type: 'tool_result', id: 'w1', content: 'ok' },
      { type: 'tool', id: 'w2', name: 'Edit', input: { file_path: '/x/b.md' } },
      { type: 'tool_result', id: 'w2', content: 'kaputt', is_error: true },
      { type: 'stats', duration_ms: 1200, out: 50, model: 'claude-opus-5-5' },
    ])
    const b = bots(s)[0]!.blocks
    expect(b.slice(-2)[0]).toMatchObject({ t: 'stats', model: 'claude-opus-5-5' })
    expect(b.slice(-1)[0]).toEqual({ t: 'files', paths: ['/x/a.md'] })
    expect(s.written).toEqual({})
  })

  it('zeigt Skills als Banner; eine gespeicherte SKILL.md zusätzlich als Werkzeug', () => {
    const s = run([
      { type: 'tool', id: 's1', name: 'Skill', input: { command: 'pdf' } },
      {
        type: 'tool',
        id: 's2',
        name: 'Write',
        input: { file_path: '/h/.claude/skills/foo/SKILL.md' },
      },
    ])
    const b = bots(s)[0]!.blocks
    expect(b[0]).toEqual({ t: 'skill', kind: 'used', label: 'pdf' })
    expect(b[1]).toEqual({ t: 'skill', kind: 'saved', label: 'foo' })
    expect(b[2]).toMatchObject({ t: 'tool', name: 'Write' })
  })

  it('eingeworfene Nachricht: eigene Blase, danach neuer Zug', () => {
    const s = run([
      { type: 'text', text: 'A' },
      { type: 'user_inject', text: 'Stopp, anders!', urls: ['/uploads/x.png'] },
      { type: 'text', text: 'B' },
    ])
    expect(s.items.map((i) => i.kind)).toEqual(['bot', 'user', 'bot'])
    expect(s.items[1]).toMatchObject({
      text: 'Stopp, anders!',
      urls: ['/uploads/x.png'],
      editable: false,
    })
    expect(bots(s)[1]!.blocks[0]).toMatchObject({ text: 'B' })
  })

  it('Nachlauf: Hinweis, dann neuer Zug', () => {
    const s = run([
      { type: 'text', text: 'Starte Build.' },
      { type: 'nachlauf', tasks: ['npm run build'] },
      { type: 'neuer_zug' },
      { type: 'text', text: 'Build fertig.' },
    ])
    expect(bots(s)).toHaveLength(2)
    expect(bots(s)[0]!.blocks.slice(-1)[0]).toMatchObject({
      t: 'note',
      note: { params: { tasks: 'npm run build' } },
    })
  })

  it('Denk-Marker steht immer oben und nur einmal', () => {
    const s = run([
      { type: 'text', text: 'x' },
      { type: 'thinking_marker' },
      { type: 'thinking_marker' },
    ])
    expect(bots(s)[0]!.blocks.map((b) => b.t)).toEqual(['thinkmark', 'text'])
  })

  it('Fehler landen als Block im Zug', () => {
    const s = run([{ type: 'error', message: 'claude nicht gefunden' }])
    expect(bots(s)[0]!.blocks).toEqual([{ t: 'error', message: 'claude nicht gefunden' }])
  })
})

describe('SseParser', () => {
  it('setzt zerstückelte Pakete zusammen und überspringt Müll', () => {
    const p = new SseParser()
    expect(p.push('data: {"type":"te')).toEqual([])
    expect(
      p.push('xt","text":"a"}\n\n: ping\n\ndata: kaputt\n\ndata: {"type":"done"}\n\n'),
    ).toEqual([{ type: 'text', text: 'a' }, { type: 'done' }])
  })
})
