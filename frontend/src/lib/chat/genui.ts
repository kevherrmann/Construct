/** Generative UI: Der Assistent kann statt Text einen Baustein schicken — als
 *  Codeblock mit der Sprache `ui` und JSON darin. Ein Codeblock statt
 *  Tool-Calling, weil CONSTRUCT über Claude Code, Hermes und fremde Modelle
 *  läuft: einen Codeblock schreibt jedes Modell. Was sich nicht lesen lässt,
 *  bleibt ein gewöhnlicher Codeblock — eine kaputte Antwort ist besser als
 *  eine verschwundene. Die Anleitung fürs Modell steht in server/genui.py. */

export interface FormField {
  name: string
  label: string
  kind: 'text' | 'textarea' | 'number' | 'date' | 'select'
  options: string[]
  required: boolean
  placeholder: string
}

export interface Series {
  name: string
  /** null = kein Wert an dieser Stelle (Lücke in der Linie, kein Balken). */
  values: (number | null)[]
}

export type ItemState = 'open' | 'active' | 'done' | 'failed'

export type UiSpec =
  | { type: 'choices'; question: string; options: string[] }
  | { type: 'event'; title: string; date: string; time: string; notes: string }
  | { type: 'form'; title: string; fields: FormField[]; submit: string }
  | {
      type: 'chart'
      kind: 'bar' | 'line'
      title: string
      unit: string
      labels: string[]
      series: Series[]
    }
  | { type: 'checklist'; title: string; items: { text: string; state: ItemState }[] }

export type Part =
  | { t: 'md'; text: string }
  | { t: 'ui'; spec: UiSpec }
  /** Ein `ui`-Block, der beim Streamen noch nicht zu Ende ist. */
  | { t: 'pending' }

const MAX_OPTIONS = 8
const MAX_FIELDS = 10
/** Mehr Reihen trennt keine Farbe mehr sicher (auch für Farbenblinde). */
export const MAX_SERIES = 4
const MAX_POINTS = 60
const MAX_ITEMS = 30
const str = (v: unknown, max = 200): string => (typeof v === 'string' ? v.trim().slice(0, max) : '')

function gueltigesDatum(d: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return false
  const dt = new Date(`${d}T00:00:00Z`)
  return !Number.isNaN(dt.getTime()) && dt.toISOString().slice(0, 10) === d
}

const obj = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null

const FIELD_KINDS = ['text', 'textarea', 'number', 'date', 'select'] as const

function parseField(v: unknown): FormField | null {
  const o = obj(v)
  if (!o) return null
  const label = str(o.label) || str(o.name)
  if (!label) return null
  const k = str(o.type) || str(o.kind)
  let kind = (FIELD_KINDS as readonly string[]).includes(k) ? (k as FormField['kind']) : 'text'
  const options = Array.isArray(o.options)
    ? [...new Set(o.options.map((x) => str(x)).filter(Boolean))].slice(0, 20)
    : []
  // Auswahl ohne Optionen: lieber ein Textfeld als eine leere Liste.
  if (kind === 'select' && !options.length) kind = 'text'
  return {
    name: str(o.name) || label,
    label,
    kind,
    options,
    required: o.required === true,
    placeholder: str(o.placeholder),
  }
}

const zahl = (v: unknown): number | null => {
  const n = typeof v === 'string' && v.trim() ? Number(v) : v
  return typeof n === 'number' && Number.isFinite(n) ? n : null
}

function parseChart(o: Record<string, unknown>): UiSpec | null {
  if (!Array.isArray(o.labels)) return null
  const labels = o.labels
    .slice(0, MAX_POINTS)
    .map((x) => (typeof x === 'number' ? String(x) : str(x, 40)))
  if (!labels.length) return null
  const title = str(o.title)
  // Eine Reihe darf auch direkt als "values" kommen.
  const roh: unknown[] = Array.isArray(o.series)
    ? o.series
    : Array.isArray(o.values)
      ? [{ name: title, values: o.values }]
      : []
  const series = roh
    .map(obj)
    .filter((x): x is Record<string, unknown> => !!x && Array.isArray(x.values))
    .slice(0, MAX_SERIES)
    .map((x, i) => ({
      name: str(x.name, 60) || (roh.length > 1 ? `#${i + 1}` : title),
      values: labels.map((_, j) => zahl((x.values as unknown[])[j])),
    }))
    .filter((x) => x.values.some((v) => v !== null))
  if (!series.length) return null
  return {
    type: 'chart',
    kind: o.kind === 'line' ? 'line' : 'bar',
    title,
    unit: str(o.unit, 20),
    labels,
    series,
  }
}

const STATES: readonly ItemState[] = ['open', 'active', 'done', 'failed']

function parseItem(v: unknown): { text: string; state: ItemState } | null {
  if (typeof v === 'string') return str(v, 300) ? { text: str(v, 300), state: 'open' } : null
  const o = obj(v)
  const text = o ? str(o.text, 300) || str(o.label, 300) : ''
  if (!o || !text) return null
  const s = str(o.state)
  const state = (STATES as readonly string[]).includes(s)
    ? (s as ItemState)
    : o.done === true
      ? 'done'
      : 'open'
  return { text, state }
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
  if (o.type === 'form') {
    if (!Array.isArray(o.fields)) return null
    const fields: FormField[] = []
    for (const f of o.fields.map(parseField)) {
      // Doppelte Namen würden sich gegenseitig überschreiben.
      if (f && !fields.some((x) => x.name === f.name)) fields.push(f)
    }
    if (!fields.length) return null
    return {
      type: 'form',
      title: str(o.title),
      fields: fields.slice(0, MAX_FIELDS),
      submit: str(o.submit, 40),
    }
  }
  if (o.type === 'chart') return parseChart(o)
  if (o.type === 'checklist') {
    if (!Array.isArray(o.items)) return null
    const items = o.items
      .map(parseItem)
      .filter((x) => x !== null)
      .slice(0, MAX_ITEMS)
    return items.length ? { type: 'checklist', title: str(o.title), items } : null
  }
  return null
}

/** Was ein abgeschicktes Formular als Nachricht schickt: Titel fett, dann je
 *  Feld eine Zeile „Label: Wert“ — lesbar für Mensch und Modell. */
export function formText(spec: Extract<UiSpec, { type: 'form' }>, values: Record<string, string>) {
  const zeilen = spec.fields
    .map((f) => [f.label, (values[f.name] ?? '').trim().replace(/\s*\n\s*/g, ' / ')] as const)
    .filter(([, v]) => v)
    .map(([l, v]) => `${l}: ${v}`)
  return [spec.title ? `**${spec.title}**` : '', ...zeilen].filter(Boolean).join('\n')
}

/** Umkehrung von formText: die Werte aus einer schon geschickten Nachricht
 *  (nach dem Neuladen). Felder, die dort nicht stehen, bleiben leer. */
export function formWerte(spec: Extract<UiSpec, { type: 'form' }>, text: string) {
  const zeilen = text.split('\n')
  const out: Record<string, string> = {}
  for (const f of spec.fields) {
    const z = zeilen.find((l) => l.startsWith(`${f.label}: `))
    if (z) out[f.name] = z.slice(f.label.length + 2)
  }
  return out
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
