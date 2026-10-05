import type { Lang } from '@/lib/bootstrap'
import { locale } from '@/lib/i18n'
import { dateYMD, parseYMD } from '../calendar/dates'

/** "heute", "gestern" oder Wochentag mit Datum. */
export function tagName(tag: string, lang: Lang, heute: (k: 'heute' | 'gestern') => string) {
  const jetzt = new Date()
  if (tag === dateYMD(jetzt)) return heute('heute')
  const gestern = new Date(jetzt)
  gestern.setDate(gestern.getDate() - 1)
  if (tag === dateYMD(gestern)) return heute('gestern')
  return parseYMD(tag).toLocaleDateString(locale(lang), {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
  })
}

/** HH:MM aus einem ISO-Zeitstempel ohne Zone ("2026-10-05T09:12:03"). */
export const uhrzeit = (ts: string) => (ts.length >= 16 ? ts.slice(11, 16) : '')

/** Der Link in den Verlauf, optional zu einer Nachricht. */
export const chatLink = (t: { session: string; project: string }, cwd: string, msg?: string) =>
  `/chat?session=${encodeURIComponent(t.session)}&project=${encodeURIComponent(t.project)}` +
  `&cwd=${encodeURIComponent(cwd)}${msg ? `&msg=${encodeURIComponent(msg)}` : ''}`
