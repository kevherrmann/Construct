// Reine Kalender-Logik ohne React — aus der alten calendar.js übernommen.
// Datumsangaben sind durchgehend "YYYY-MM-DD"-Strings in ORTSZEIT: so lassen
// sie sich direkt mit events.json vergleichen und lexikografisch sortieren.
import type { CalEvent } from '@/api/calendar'
import type { Lang } from '@/lib/bootstrap'

const MONTHS: Record<Lang, string[]> = {
  de: [
    'Januar',
    'Februar',
    'März',
    'April',
    'Mai',
    'Juni',
    'Juli',
    'August',
    'September',
    'Oktober',
    'November',
    'Dezember',
  ],
  en: [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ],
}
const DOW: Record<Lang, string[]> = {
  de: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'],
  en: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
}

/** Monatsname, m 0-basiert. */
export const monthName = (lang: Lang, m: number) => MONTHS[lang][m]!
/** Wochentage ab Montag. */
export const weekdays = (lang: Lang) => DOW[lang]

const pad2 = (n: number) => String(n).padStart(2, '0')
/** m 0-basiert, wie bei Date. */
export const ymd = (y: number, m: number, d: number) => `${y}-${pad2(m + 1)}-${pad2(d)}`
export const dateYMD = (dt: Date) => ymd(dt.getFullYear(), dt.getMonth(), dt.getDate())
export const todayYMD = () => dateYMD(new Date())
/** "YYYY-MM-DD" → lokales Date um Mitternacht (nicht new Date(ds): das wäre UTC). */
export function parseYMD(ds: string) {
  const [y, m, d] = ds.split('-').map(Number)
  return new Date(y!, m! - 1, d!)
}

// Findet e am Tag ds statt? Jährliche (Geburtstage) matchen über Monat-Tag, Jahr egal.
export const occursOn = (e: CalEvent, ds: string) =>
  e.repeat === 'yearly' ? e.date.slice(5) === ds.slice(5) : e.date === ds

// Termine eines Tages nach Uhrzeit. Das '~' sollte ganztägige ans Ende
// schieben — localeCompare sortiert Satzzeichen aber VOR Ziffern, darum stehen
// sie tatsächlich vorn. So kennt man es aus der alten Oberfläche; bleibt so.
export const eventsOn = (events: CalEvent[], ds: string) =>
  events.filter((e) => occursOn(e, ds)).sort((a, b) => (a.time || '~').localeCompare(b.time || '~'))

// Nächstes Vorkommen ab fromStr (für die "Anstehend"-Liste): jährliche aufs nächste Jahr rollen.
export function occDate(e: CalEvent, fromStr: string) {
  if (e.repeat !== 'yearly') return e.date
  const md = e.date.slice(5)
  const y = +fromStr.slice(0, 4)
  const cand = `${y}-${md}`
  return cand < fromStr ? `${y + 1}-${md}` : cand
}

/** Die nächsten `limit` Termine ab heute, jeder auf sein nächstes Vorkommen abgebildet. */
export function upcoming(events: CalEvent[], today: string, limit = 15) {
  return events
    .map((e) => ({ e, d: occDate(e, today) }))
    .filter((x) => x.d >= today)
    .sort((a, b) => (a.d + (a.e.time || '~')).localeCompare(b.d + (b.e.time || '~')))
    .slice(0, limit)
}

export interface GridDay {
  ds: string
  day: number
  /** Tag aus dem Vor- oder Folgemonat (gedimmt). */
  other: boolean
}

// Sichtbarer Bereich des Grids: 6 Wochen ab dem Montag vor dem 1. — immer
// 42 Zellen, damit die Höhe beim Blättern nicht springt.
export function monthGrid(year: number, month: number): GridDay[] {
  const first = new Date(year, month, 1)
  const startDow = (first.getDay() + 6) % 7 // Montag = 0
  return Array.from({ length: 42 }, (_, i) => {
    // Über den Konstruktor rechnen statt Millisekunden addieren: so stolpert
    // die Zeitumstellung nicht über eine fehlende oder doppelte Stunde.
    const dt = new Date(year, month, 1 - startDow + i)
    return { ds: dateYMD(dt), day: dt.getDate(), other: dt.getMonth() !== month }
  })
}

/** Erster und letzter Tag des Grids (für /api/activity). */
export function gridRange(year: number, month: number): [string, string] {
  const g = monthGrid(year, month)
  return [g[0]!.ds, g[41]!.ds]
}

export const baseName = (p: string) => p.split('/').filter(Boolean).pop() || p || '?'
