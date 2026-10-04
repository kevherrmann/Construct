import type { Block, ChatItem } from '@/lib/chat/types'
import type { StationId } from './stationen'

// Was tut die Figur gerade? Aus dem Chat-Zustand abgeleitet — dieselben
// Ereignisse, die der Chat als Text zeigt, werden hier zu einer Lage: Pose,
// Station, die leuchtet, und eine kurze Zeile für die Sprechblase.

export type Phase =
  | 'ruht'
  | 'denkt'
  | 'liest'
  | 'sucht'
  | 'schreibt'
  | 'terminal'
  | 'recherchiert'
  | 'delegiert'
  | 'werkzeug'
  | 'antwortet'
  | 'wartet'

export interface Lage {
  phase: Phase
  /** Station, die gerade leuchtet (null = keine). */
  station: StationId | null
  /** Datei, Befehl, Suchbegriff … (kurz). */
  detail: string
  /** Text der letzten Antwort, ohne Markdown-Zeichen. */
  text: string
  /** Dieselbe Antwort als Markdown für die Sprechblase (Code als Chip). */
  md: string
  /** Antwort läuft noch. */
  live: boolean
}

interface Werkzeug {
  phase: Phase
  station: StationId
}

// Claude-Code-Werkzeuge und die von Hermes, auf Stationen verteilt.
const WERKZEUGE: Record<string, Werkzeug> = {
  Read: { phase: 'liest', station: 'regal' },
  read_file: { phase: 'liest', station: 'regal' },
  Glob: { phase: 'sucht', station: 'regal' },
  Grep: { phase: 'sucht', station: 'regal' },
  search_files: { phase: 'sucht', station: 'regal' },
  LS: { phase: 'sucht', station: 'regal' },
  Write: { phase: 'schreibt', station: 'werkbank' },
  Edit: { phase: 'schreibt', station: 'werkbank' },
  MultiEdit: { phase: 'schreibt', station: 'werkbank' },
  NotebookEdit: { phase: 'schreibt', station: 'werkbank' },
  write_file: { phase: 'schreibt', station: 'werkbank' },
  patch: { phase: 'schreibt', station: 'werkbank' },
  Bash: { phase: 'terminal', station: 'monitore' },
  BashOutput: { phase: 'terminal', station: 'monitore' },
  KillShell: { phase: 'terminal', station: 'monitore' },
  terminal: { phase: 'terminal', station: 'monitore' },
  execute_code: { phase: 'terminal', station: 'monitore' },
  WebFetch: { phase: 'recherchiert', station: 'monitore' },
  WebSearch: { phase: 'recherchiert', station: 'monitore' },
  web_search: { phase: 'recherchiert', station: 'monitore' },
  web_extract: { phase: 'recherchiert', station: 'monitore' },
  Task: { phase: 'delegiert', station: 'archiv' },
  Agent: { phase: 'delegiert', station: 'archiv' },
  delegate_task: { phase: 'delegiert', station: 'archiv' },
  Skill: { phase: 'werkzeug', station: 'werkzeug' },
  skill_view: { phase: 'werkzeug', station: 'werkzeug' },
}

function werkzeug(name: string): Werkzeug {
  // Anzeigenamen wie "Write: index.html" (Hermes) → "Write"
  const kern = name.split(/[:\s]/)[0] ?? name
  if (kern.startsWith('mcp__')) return { phase: 'werkzeug', station: 'steckfeld' }
  if (kern.startsWith('browser_')) return { phase: 'recherchiert', station: 'monitore' }
  return WERKZEUGE[kern] ?? { phase: 'werkzeug', station: 'werkbank' }
}

const kurz = (s: string, n = 64) => (s.length > n ? s.slice(0, n - 1) + '…' : s)
const dateiname = (p: string) => p.split('/').filter(Boolean).pop() ?? p

/** Was beim Werkzeug kurz dabeistehen soll. */
export function werkzeugDetail(name: string, input: unknown): string {
  const i = (input && typeof input === 'object' ? input : {}) as Record<string, unknown>
  const pfad = i.file_path ?? i.path ?? i.notebook_path
  if (typeof pfad === 'string' && pfad) return dateiname(pfad)
  if (typeof i.command === 'string') return kurz(i.command.split('\n')[0] ?? '')
  if (typeof i.pattern === 'string') return kurz(i.pattern)
  if (typeof i.query === 'string') return kurz(i.query)
  if (typeof i.url === 'string') return kurz(i.url.replace(/^https?:\/\//, ''))
  if (typeof i.description === 'string') return kurz(i.description)
  // Hermes: "write_file: taschenrechner.html"
  const nachDoppelpunkt = name.split(':').slice(1).join(':').trim()
  return kurz(nachDoppelpunkt)
}

/** Markdown grob zu Fließtext — für die Sprechblase reicht das. */
export function klartext(md: string): string {
  return (
    md
      .replace(/```[\s\S]*?(```|$)/g, ' [Code] ')
      .replace(/`([^`]*)`/g, '$1')
      .replace(/!\[[^\]]*\]\([^)]*\)/g, ' [Bild] ')
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+/gm, '')
      // Tabellen: Trennzeilen weg, Zellen mit Punkt verbinden
      .replace(/^[ \t]*\|?[ \t]*:?-{2,}.*$/gm, '')
      .replace(/^[ \t]*\|(.*)\|[ \t]*$/gm, (_, z: string) =>
        z
          .split('|')
          .map((c) => c.trim())
          .filter(Boolean)
          .join(' · '),
      )
      .replace(/[*_~]{1,3}([^*_~]+)[*_~]{1,3}/g, '$1')
      .replace(/[ \t]+/g, ' ')
      .replace(/\n{2,}/g, '\n')
      .trim()
  )
}

/** Markdown für die Sprechblase: Code-Blöcke werden zu einem kleinen Chip
 *  (der ganze Code steht im Protokoll), der Rest bleibt, wie er ist. */
export function blasenMd(md: string): string {
  return md.replace(/```([^\n`]*)\n?([\s\S]*?)(```|$)/g, (_, sprache: string, code: string) => {
    const n = code.replace(/\n$/, '').split('\n').length
    const was = sprache.trim() || 'Code'
    return `\n\n\`⌗ ${was} · ${n} ${n === 1 ? 'Zeile' : 'Zeilen'}\`\n\n`
  })
}

/**
 * Antwort in Abschnitte für die Sprechblase: wie Untertitel steht dort immer
 * nur einer, der Rest ist einen Klick entfernt. Grenzen sind Leerzeilen;
 * Überschriften gehören zum Folgenden, sehr kurze Stücke werden mit dem
 * nächsten zusammengelegt. Tabellen und Listen bleiben am Stück.
 */
export function abschnitte(md: string, min = 220): string[] {
  const bloecke = md
    .split(/\n[ \t]*\n+/)
    .map((b) => b.trim())
    .filter(Boolean)
  const out: string[] = []
  let acc = ''
  for (const b of bloecke) {
    acc = acc ? `${acc}\n\n${b}` : b
    const nurUeberschrift = /^#{1,6}\s/.test(b) && !b.includes('\n')
    const endetMitDoppelpunkt = /:\s*$/.test(b)
    if (!nurUeberschrift && !endetMitDoppelpunkt && acc.length >= min) {
      out.push(acc)
      acc = ''
    }
  }
  if (acc) {
    // Kurzer Rest: an den letzten Abschnitt hängen, sonst eigener
    if (out.length && acc.length < min / 2) out[out.length - 1] += `\n\n${acc}`
    else out.push(acc)
  }
  return out
}

function antwortMd(blocks: Block[], markdown?: string): string {
  return (
    markdown ??
    blocks
      .filter((b): b is Extract<Block, { t: 'text' }> => b.t === 'text')
      .map((b) => b.text)
      .join('\n\n')
  )
}

/**
 * Lage aus den Einträgen der aktiven Unterhaltung (Verlauf + laufender Teil).
 * busy/nachlauf wie im Chat-Store.
 */
export function lageAus(items: ChatItem[], busy: boolean, nachlauf: boolean): Lage {
  let bot: Extract<ChatItem, { kind: 'bot' }> | undefined
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i]!
    if (it.kind === 'bot') {
      bot = it
      break
    }
    if (it.kind === 'user') break // neue Frage, noch keine Antwort darauf
  }
  const roh = bot ? antwortMd(bot.blocks, bot.markdown) : ''
  const text = klartext(roh)
  const md = blasenMd(roh)
  const ruhe: Lage = { phase: 'ruht', station: null, detail: '', text, md, live: false }
  if (nachlauf) return { ...ruhe, phase: 'wartet' }
  if (!busy) return ruhe
  if (!bot || bot.thinking) return { ...ruhe, phase: 'denkt', live: true }
  const letzter = bot.blocks[bot.blocks.length - 1]
  if (letzter?.t === 'tool' && !letzter.result) {
    const w = werkzeug(letzter.name)
    return {
      phase: w.phase,
      station: w.station,
      detail: werkzeugDetail(letzter.name, letzter.input),
      text,
      md,
      live: true,
    }
  }
  if (letzter?.t === 'text') return { ...ruhe, phase: 'antwortet', live: true }
  return { ...ruhe, phase: 'denkt', live: true }
}
