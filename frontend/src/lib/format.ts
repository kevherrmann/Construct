export const baseName = (p?: string | null) =>
  (p ?? '').split('/').filter(Boolean).pop() || p || '?'

export const fmtNum = (n?: number | null) =>
  n == null
    ? '?'
    : n >= 1000
      ? (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, '') + 'k'
      : String(n)

export function fmtDur(ms?: number | null) {
  if (ms == null) return '?'
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} s`
  return `${Math.floor(s / 60)} m ${Math.round(s % 60)} s`
}

/** Zeit aus dem Verlauf -> ms: ISO-Text oder Unix-Sekunden. */
export function parseTs(v?: string | number | null): number | undefined {
  if (v == null || v === '') return undefined
  const n = typeof v === 'number' ? (v < 1e12 ? v * 1000 : v) : Date.parse(v)
  return Number.isFinite(n) ? n : undefined
}

// toLocale*String legt bei jedem Aufruf einen neuen Formatierer an — teuer,
// wenn ein langer Verlauf neu zeichnet. Darum je Sprache und Form einer.
const FORMATE = new Map<string, Intl.DateTimeFormat>()
export function datumsFormat(lang: string | undefined, opts: Intl.DateTimeFormatOptions) {
  const key = `${lang ?? ''}|${JSON.stringify(opts)}`
  let f = FORMATE.get(key)
  if (!f) {
    f = new Intl.DateTimeFormat(lang, opts)
    FORMATE.set(key, f)
  }
  return f
}

/** Uhrzeit neben der Nachricht: "21:14", an anderen Tagen "28.09. 21:14". */
export function fmtMsgTime(ts: number, lang?: string, now = Date.now()) {
  const d = new Date(ts)
  const time = datumsFormat(lang, { hour: '2-digit', minute: '2-digit' }).format(d)
  if (d.toDateString() === new Date(now).toDateString()) return time
  const sameYear = d.getFullYear() === new Date(now).getFullYear()
  const date = datumsFormat(lang, {
    day: '2-digit',
    month: '2-digit',
    ...(sameYear ? {} : { year: '2-digit' }),
  }).format(d)
  return `${date} ${time}`
}

/** Bilder zeigt der Chat als Vorschau, alle anderen Anhänge als Datei-Chip. */
export const isImage = (u?: string) => /\.(png|jpe?g|gif|webp|bmp|svg|heic)$/i.test(u ?? '')

/** Endung in Großbuchstaben (PDF, ODT …), leer ohne Endung. */
export const fileExt = (u?: string) => /\.([a-z0-9]+)$/i.exec(u ?? '')?.[1]?.toUpperCase() ?? ''

/** Bytes als GB (mit Komma, eine Stelle) bzw. MB — wie in der alten Oberfläche. */
export const fmtGB = (n: number) =>
  n >= 1e9 ? (n / 1e9).toFixed(1).replace('.', ',') + ' GB' : Math.round((n || 0) / 1e6) + ' MB'

/** Prozent eines Fortschritts, 0 ohne bekannte Gesamtgröße. */
export const pct = (p: { total: number; completed: number }) =>
  p.total ? Math.round((p.completed / p.total) * 100) : 0

/**
 * Wie lange die letzte Update-Prüfung her ist: 'now' | {min} | {h}.
 * Getrennt vom Text, damit die Übersetzung die Zahl einsetzen kann.
 */
export function ago(lastCheck: number, now = Date.now() / 1000) {
  const min = Math.round((now - lastCheck) / 60)
  if (min < 1) return { unit: 'now' as const, n: 0 }
  if (min < 60) return { unit: 'min' as const, n: min }
  return { unit: 'h' as const, n: Math.round(min / 60) }
}
