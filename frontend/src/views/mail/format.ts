import type { MailAccount, MailSummary } from '@/api/mail'
import type { MailFilter } from './mailStore'

// Kontofarben sind Unterscheidungsfarben, keine Theme-Farben: die ersten
// beiden folgen dem Theme, die übrigen bleiben fest (wie in der alten Oberfläche).
const MAIL_COLORS = ['var(--green)', 'var(--link)', '#ffd24a', '#7fb2ff', '#ff9bd2', '#c9ff7f']

export function accColor(accounts: MailAccount[], email: string) {
  const i = accounts.findIndex((a) => a.email === email)
  return MAIL_COLORS[(i < 0 ? 0 : i) % MAIL_COLORS.length]!
}

export const accName = (email: string) => (email || '').split('@')[0] ?? ''

export const fmtSize = (n: number) =>
  n >= 1048576
    ? (n / 1048576).toFixed(1) + ' MB'
    : n >= 1024
      ? Math.round(n / 1024) + ' kB'
      : n + ' B'

/** Heute → Uhrzeit, dieses Jahr → TT.MM., sonst TT.MM.JJ. */
export function fmtMailDate(ts: number, loc: string, now = new Date()) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' })
  const s = d.toLocaleDateString(loc, { day: '2-digit', month: '2-digit' })
  return d.getFullYear() === now.getFullYear() ? s : s + String(d.getFullYear()).slice(2)
}

/**
 * Kategorisierte Mails verschwinden aus dem Posteingang und leben nur noch in
 * ihrer Kategorie. Ausnahme: bei aktiver Suche wird ÜBERALL gesucht.
 */
export function mailVisible(msgs: MailSummary[], f: MailFilter) {
  const q = (f.q || '').trim().toLowerCase()
  return msgs.filter(
    (m) =>
      (!f.acc || m.account === f.acc) &&
      (f.cat ? m.category === f.cat : q ? true : !m.category) &&
      (!q ||
        `${m.from_name || ''} ${m.from_addr || ''} ${m.subject || ''} ${m.category || ''} ${m.account}`
          .toLowerCase()
          .includes(q)),
  )
}

/** "Re: " nur, wenn nicht schon da. */
export const replySubject = (s: string) => (/^re:/i.test(s || '') ? s : 'Re: ' + (s || ''))
export const fwdSubject = (s: string) => (/^(fwd|wg):/i.test(s || '') ? s : 'Fwd: ' + (s || ''))
export const quote = (text: string) =>
  (text || '')
    .split('\n')
    .map((l) => '> ' + l)
    .join('\n')

/**
 * HTML-Mail für das Sandbox-iframe: keine Skripte (sandbox ohne allow-scripts),
 * Links öffnen außerhalb in neuem Fenster — nie ins App-DOM einsetzen.
 */
export const mailSrcdoc = (html: string) =>
  '<base target="_blank"><style>body{font-family:sans-serif;margin:12px;word-break:break-word}</style>' +
  html
