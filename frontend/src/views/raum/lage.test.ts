import { describe, expect, it } from 'vitest'
import type { ChatItem } from '@/lib/chat/types'
import { abschnitte, blasenMd, klartext, lageAus, werkzeugDetail } from './lage'

const user = (text: string): ChatItem => ({ kind: 'user', id: 'u', text, urls: [], editable: true })
const bot = (blocks: Extract<ChatItem, { kind: 'bot' }>['blocks'], thinking = false): ChatItem => ({
  kind: 'bot',
  id: 'b',
  blocks,
  thinking,
})

describe('lageAus', () => {
  it('ruht ohne Lauf und zeigt die letzte Antwort', () => {
    const l = lageAus(
      [user('hi'), bot([{ t: 'text', text: '**Hallo** Welt', streaming: false }])],
      false,
      false,
    )
    expect(l).toMatchObject({ phase: 'ruht', station: null, text: 'Hallo Welt', live: false })
  })

  it('zeigt die Ticket-Markerzeile nicht, auch nicht halb gestreamt', () => {
    const fertig = lageAus(
      [
        user('hi'),
        bot([{ t: 'text', text: 'Erledigt.\n\n[[ticket neu: Raum prüfen]]', streaming: false }]),
      ],
      false,
      false,
    )
    expect(fertig).toMatchObject({ text: 'Erledigt.', md: 'Erledigt.' })
    const halb = lageAus(
      [user('hi'), bot([{ t: 'text', text: 'Erledigt.\n\n[[tick', streaming: true }])],
      true,
      false,
    )
    expect(halb.md).toBe('Erledigt.')
  })

  it('denkt, solange noch nichts kam', () => {
    expect(lageAus([user('hi')], true, false).phase).toBe('denkt')
    expect(lageAus([user('hi'), bot([], true)], true, false).phase).toBe('denkt')
  })

  it('offenes Werkzeug bestimmt Station und Detail', () => {
    const l = lageAus(
      [user('x'), bot([{ t: 'tool', name: 'Read', input: { file_path: '/a/b/server.py' } }])],
      true,
      false,
    )
    expect(l).toMatchObject({ phase: 'liest', station: 'regal', detail: 'server.py' })
    const t = lageAus(
      [
        user('x'),
        bot([{ t: 'tool', name: 'Bash', input: { command: 'npm run build\nnpm test' } }]),
      ],
      true,
      false,
    )
    expect(t).toMatchObject({ phase: 'terminal', station: 'monitore', detail: 'npm run build' })
  })

  it('abgeschlossenes Werkzeug zählt nicht mehr als aktiv', () => {
    const l = lageAus(
      [
        user('x'),
        bot([
          { t: 'tool', name: 'Write', input: {}, result: { content: 'ok', isError: false } },
          { t: 'text', text: 'Fertig', streaming: true },
        ]),
      ],
      true,
      false,
    )
    expect(l.phase).toBe('antwortet')
  })

  it('MCP und Hermes-Namen', () => {
    const mcp = lageAus(
      [user('x'), bot([{ t: 'tool', name: 'mcp__github__search', input: {} }])],
      true,
      false,
    )
    expect(mcp.station).toBe('steckfeld')
    const h = lageAus(
      [user('x'), bot([{ t: 'tool', name: 'write_file: rechner.html', input: {} }])],
      true,
      false,
    )
    expect(h).toMatchObject({ phase: 'schreibt', station: 'werkbank', detail: 'rechner.html' })
  })

  it('Schritte eines Helfers bewegen die Figur nicht, sie wartet am Platz', () => {
    const l = lageAus(
      [
        user('x'),
        bot([
          { t: 'tool', id: 'a1', name: 'Agent', input: { description: 'Dateien lesen' } },
          { t: 'tool', id: 'r1', name: 'Read', input: { file_path: '/a/eins.txt' }, parent: 'a1' },
        ]),
      ],
      true,
      false,
    )
    expect(l).toMatchObject({ phase: 'delegiert', station: null, detail: 'Dateien lesen' })
  })

  it('Nachlauf heißt warten', () => {
    expect(lageAus([user('x')], false, true).phase).toBe('wartet')
  })

  it('neue Frage ohne Antwort zeigt keinen alten Text', () => {
    const l = lageAus(
      [bot([{ t: 'text', text: 'alt', streaming: false }]), user('neu')],
      true,
      false,
    )
    expect(l.text).toBe('')
  })
})

describe('Hilfen', () => {
  it('klartext entfernt Markdown', () => {
    expect(klartext('# Titel\n- **fett** und `code`\n```js\nx\n```\n[Link](http://a)')).toBe(
      'Titel\nfett und code\n [Code] \nLink',
    )
  })
  it('klartext macht aus Tabellen lesbare Zeilen', () => {
    expect(klartext('| Teil | Inhalt |\n|---|---|\n| Hero | Name |')).toBe(
      'Teil · Inhalt\nHero · Name',
    )
  })
  it('werkzeugDetail kürzt lange Befehle', () => {
    expect(werkzeugDetail('Bash', { command: 'x'.repeat(100) }).length).toBe(64)
  })
})

describe('blasenMd', () => {
  it('lässt kurzen Code zum Kopieren stehen', () => {
    const md = 'Schau:\n\n```bash\nnpm run build\n```\n\n**fertig**'
    expect(blasenMd(md)).toBe(md)
  })

  it('macht aus langen Code-Blöcken einen Chip und lässt den Rest stehen', () => {
    const code = Array.from({ length: 20 }, (_, i) => `print(${i})`).join('\n')
    const md = blasenMd(`Schau:\n\n\`\`\`python\n${code}\n\`\`\`\n\n**fertig**`)
    expect(md).toContain('`⌗ python · 20 Zeilen`')
    expect(md).not.toContain('print(1)')
    expect(md).toContain('**fertig**')
  })

  it('kommt mit einem noch offenen Block beim Streamen klar', () => {
    expect(blasenMd('Gleich:\n```\nnoch nicht fertig')).toContain('noch nicht fertig')
  })
})

describe('abschnitte', () => {
  const absatz = (n: number) => 'Wort '.repeat(n).trim() + '.'

  it('teilt an Leerzeilen und legt kurze Stücke zusammen', () => {
    const a = abschnitte(`${absatz(60)}\n\nKurz.\n\n${absatz(60)}`)
    expect(a).toHaveLength(2)
    expect(a[1]).toMatch(/^Kurz\./)
  })

  it('Überschrift und Einleitung mit Doppelpunkt bleiben beim Folgenden', () => {
    const a = abschnitte(`## Plan\n\nSo gehts:\n\n- eins\n- zwei\n\n${absatz(80)}`, 20)
    expect(a[0]).toContain('## Plan')
    expect(a[0]).toContain('- zwei')
  })

  it('teilt nicht mitten im Code-Block', () => {
    const code = '```python\na = 1\n\n\nb = 2\n```'
    const a = abschnitte(`${absatz(60)}\n\n${code}\n\n${absatz(60)}`)
    expect(a.some((t) => t.includes(code))).toBe(true)
  })

  it('ein kurzer Rest hängt am letzten Abschnitt', () => {
    expect(abschnitte(`${absatz(60)}\n\nOk?`)).toHaveLength(1)
    expect(abschnitte('')).toEqual([])
  })
})
