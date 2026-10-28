/** Generative UI: Der Assistent kann statt Text einen Baustein schicken — als
 *  Codeblock mit der Sprache `ui` und JSON darin. Ein Codeblock statt
 *  Tool-Calling, weil CONSTRUCT über Claude Code, Hermes und fremde Modelle
 *  läuft: einen Codeblock schreibt jedes Modell. Was sich nicht lesen lässt,
 *  bleibt ein gewöhnlicher Codeblock — eine kaputte Antwort ist besser als
 *  eine verschwundene. Die Anleitung fürs Modell steht in server/genui.py. */

export type UiSpec =
  | { type: 'choices'; question: string; options: string[] }
  | { type: 'event'; title: string; date: string; time: string; notes: string }

export type Part =
  | { t: 'md'; text: string }
  | { t: 'ui'; spec: UiSpec }
  /** Ein `ui`-Block, der beim Streamen noch nicht zu Ende ist. */
  | { t: 'pending' }

const MAX_OPTIONS = 8
const str = (v: unknown, max = 200): string => (typeof v === 'string' ? v.trim().slice(0, max) : '')

function gueltigesDatum(d: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return false
  const dt = new Date(`${d}T00:00:00Z`)
  return !Number.isNaN(dt.getTime()) && dt.toISOString().slice(0, 10) === d
}

/** JSON → Baustein, oder null, wenn etwas fehlt oder nicht passt. */
export function parseSpec(json: string): UiSpec | null {
  let raw: unknown
  try {
    raw = JSON.parse(json)
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const o = raw as Record<string, unknown>
  if (o.type === 'choices') {
    if (!Array.isArray(o.options)) return null
    // Manche Modelle schreiben [{"label": "…"}] statt ["…"].
    const options = o.options
      .map((x) =>
        typeof x === 'string'
          ? str(x)
          : x && typeof x === 'object'
            ? str((x as Record<string, unknown>).label)
            : '',
      )
      .filter(Boolean)
    const unique = [...new Set(options)].slice(0, MAX_OPTIONS)
    return unique.length
      ? { type: 'choices', question: str(o.question, 300), options: unique }
      : null
  }
  if (o.type === 'event') {
    const title = str(o.title)
    const date = str(o.date)
    let time = str(o.time)
    if (time) {
      const [, h = '', min = ''] = time.match(/^(\d{1,2}):(\d{2})$/) ?? []
      if (!h || +h > 23 || +min > 59) return null
      time = `${h.padStart(2, '0')}:${min}`
    }
    if (!title || !gueltigesDatum(date)) return null
    return { type: 'event', title, date, time, notes: str(o.notes, 1000) }
  }
  return null
}

// Eröffnung und Abschluss eines Codeblocks, höchstens drei Leerzeichen
// eingerückt wie bei CommonMark.
const OPEN = /^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)/
const close = (fence: string) => new RegExp(`^ {0,3}${fence[0]}{${fence.length},}[ \\t]*$`)

/** Antworttext in Markdown-Stücke und Bausteine zerlegen. Andere Codeblöcke
 *  werden übersprungen — ein ```ui als Beispiel in einem ````markdown-Block
 *  bleibt Text. */
export function splitUi(text: string, streaming = false): Part[] {
  if (!text.includes('ui')) return [{ t: 'md', text }]
  const lines = text.split('\n')
  const parts: Part[] = []
  let md: string[] = []
  const flush = () => {
    const s = md.join('\n')
    if (s.trim()) parts.push({ t: 'md', text: s })
    md = []
  }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? ''
    const [, fence, lang] = line.match(OPEN) ?? []
    if (!fence) {
      md.push(line)
      continue
    }
    const end = close(fence)
    let j = i + 1
    while (j < lines.length && !end.test(lines[j] ?? '')) j++
    const offen = j >= lines.length
    if (lang !== 'ui') {
      // Fremder Codeblock: unverändert durchreichen.
      md.push(...lines.slice(i, j + 1))
      i = j
      continue
    }
    if (offen && streaming) {
      flush()
      parts.push({ t: 'pending' })
      return parts
    }
    const body = lines.slice(i + 1, j).join('\n')
    const spec = offen ? null : parseSpec(body)
    if (spec) {
      flush()
      parts.push({ t: 'ui', spec })
    } else {
      md.push('```json', body, '```')
    }
    i = j
  }
  flush()
  return parts
}

/** Antwort ohne Bausteine — zum Vorlesen. */
export const ohneUi = (text: string): string =>
  splitUi(text)
    .map((p) => (p.t === 'md' ? p.text : ''))
    .join('\n')
