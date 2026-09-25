import type { MailSummary } from '@/api/mail'
import {
  fmtMailDate,
  fmtSize,
  fwdSubject,
  mailSrcdoc,
  mailVisible,
  quote,
  replySubject,
} from './format'

const m = (p: Partial<MailSummary>): MailSummary => ({
  account: 'a@gmx.de',
  folder: 'INBOX',
  uid: '1',
  key: 'k1',
  from_name: 'Anna',
  from_addr: 'anna@x.de',
  to: '',
  subject: 'Hallo',
  ts: 0,
  seen: true,
  category: '',
  ...p,
})

describe('mailVisible', () => {
  const msgs = [
    m({ uid: '1', subject: 'Rechnung Mai', category: '🧾 Rechnungen' }),
    m({ uid: '2', subject: 'Treffen' }),
    m({ uid: '3', account: 'b@gmail.com', subject: 'Rechnung Juni' }),
  ]
  const f = { acc: '', cat: '', q: '' }

  it('Posteingang zeigt nur Mails ohne Kategorie', () => {
    expect(mailVisible(msgs, f).map((x) => x.uid)).toEqual(['2', '3'])
  })
  it('Kategorie zeigt nur ihre Mails', () => {
    expect(mailVisible(msgs, { ...f, cat: '🧾 Rechnungen' }).map((x) => x.uid)).toEqual(['1'])
  })
  it('Suche geht über alle Kategorien', () => {
    expect(mailVisible(msgs, { ...f, q: 'rechnung' }).map((x) => x.uid)).toEqual(['1', '3'])
  })
  it('Kontofilter', () => {
    expect(mailVisible(msgs, { ...f, acc: 'b@gmail.com' }).map((x) => x.uid)).toEqual(['3'])
  })
})

describe('Formatierung', () => {
  it('fmtSize', () => {
    expect(fmtSize(512)).toBe('512 B')
    expect(fmtSize(2048)).toBe('2 kB')
    expect(fmtSize(3 * 1048576)).toBe('3.0 MB')
  })
  it('fmtMailDate: heute Uhrzeit, dieses Jahr ohne, sonst mit Jahr', () => {
    const now = new Date(2026, 8, 25, 18, 0)
    expect(fmtMailDate(new Date(2026, 8, 25, 9, 5).getTime() / 1000, 'de-DE', now)).toBe('09:05')
    expect(fmtMailDate(new Date(2026, 2, 3).getTime() / 1000, 'de-DE', now)).toBe('03.03.')
    expect(fmtMailDate(new Date(2024, 2, 3).getTime() / 1000, 'de-DE', now)).toBe('03.03.24')
    expect(fmtMailDate(0, 'de-DE', now)).toBe('')
  })
  it('Betreff-Präfixe nicht doppeln', () => {
    expect(replySubject('Hallo')).toBe('Re: Hallo')
    expect(replySubject('RE: Hallo')).toBe('RE: Hallo')
    expect(fwdSubject('WG: x')).toBe('WG: x')
    expect(fwdSubject('x')).toBe('Fwd: x')
  })
  it('quote und srcdoc', () => {
    expect(quote('a\nb')).toBe('> a\n> b')
    expect(mailSrcdoc('<p>x</p>')).toMatch(/^<base target="_blank">.*<p>x<\/p>$/)
  })
})
