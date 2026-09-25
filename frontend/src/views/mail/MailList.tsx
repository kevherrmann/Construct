import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import {
  FETCH_ERROR,
  errText,
  mailApi,
  patchMailList,
  refreshMailList,
  type MailSummary,
} from '@/api/mail'
import { accColor, accName, fmtMailDate, mailVisible } from './format'
import { mailKey, useMailStore } from './mailStore'
import { useLocale, useMail, useServerText } from './useMail'
import { useDeleteMail } from './useDeleteMail'
import shared from './shared.module.css'
import s from './MailList.module.css'

// DOM klein halten — tausende Zeilen auf einmal ruckeln.
const CHUNK = 400

export function MailList() {
  const { t } = useTranslation()
  const st = useServerText()
  const nav = useNavigate()
  const qc = useQueryClient()
  const loc = useLocale()
  const { accounts, accountsQ, categories, msgs, errors, loaded, listQ } = useMail()
  const { filter, sel, setFilter, setSel, toggle } = useMailStore()
  const delMail = useDeleteMail()
  const [busy, setBusy] = useState<'' | 'del' | 'cat'>('')
  // Wie viele Zeilen gezeigt werden; zurück auf CHUNK, sobald sich der Filter ändert.
  const [shown, setShown] = useState({ key: '', n: CHUNK })

  const list = useMemo(() => mailVisible(msgs, filter), [msgs, filter])
  const fkey = `${filter.acc}|${filter.cat}|${filter.q}`
  const limit = shown.key === fkey ? shown.n : CHUNK
  const allSel = list.length > 0 && list.every((m) => sel.has(mailKey(m)))

  if (listQ.isFetching)
    return (
      <div className={`${shared.tool} ${shared.loading}`}>
        {t(
          '⟲ Rufe Postfächer ab … es werden ALLE Mails geladen — bei großen Postfächern kann das eine Minute dauern.',
        )}
      </div>
    )

  const selectAll = () => {
    const next = new Set(sel)
    list.forEach((m) => (allSel ? next.delete(mailKey(m)) : next.add(mailKey(m))))
    setSel(next)
  }

  const catSelected = async (cat: string) => {
    const chosen = msgs.filter((m) => sel.has(mailKey(m)))
    const keys = chosen.map((m) => m.key).filter(Boolean)
    if (!keys.length) return
    setBusy('cat')
    try {
      await mailApi.categorizeMany(keys, cat)
    } catch (e) {
      window.alert(t('Kategorisieren fehlgeschlagen:') + ' ' + st(errText(e)))
      setBusy('')
      return
    }
    const done = new Set(chosen.map(mailKey))
    patchMailList(qc, (ms) => ms.map((m) => (done.has(mailKey(m)) ? { ...m, category: cat } : m)))
    setSel(new Set()) // Auswahl nach Zuweisung aufheben
    setBusy('')
  }

  const delSelected = async () => {
    const items = msgs
      .filter((m) => sel.has(mailKey(m)))
      .map((m) => ({ account: m.account, uid: m.uid, folder: m.folder || 'INBOX' }))
    if (!items.length) return
    if (
      !window.confirm(
        t('{n} E-Mail(s) wirklich löschen?', { n: items.length }) +
          '\n\n' +
          t('Sie werden auch auf den Mail-Servern in den Papierkorb verschoben.'),
      )
    )
      return
    setBusy('del')
    let res
    try {
      res = await mailApi.deleteMany(items)
    } catch (e) {
      window.alert(t('Löschen fehlgeschlagen:') + ' ' + st(errText(e)))
      setBusy('')
      return
    }
    // Bei Teilfehlern bleiben die Mails der betroffenen Konten in Liste & Auswahl.
    const failed = Object.keys(res.errors ?? {})
    const gone = new Set(items.filter((i) => !failed.includes(i.account)).map(mailKey))
    patchMailList(qc, (ms) => ms.filter((m) => !gone.has(mailKey(m))))
    setSel(new Set([...useMailStore.getState().sel].filter((k) => !gone.has(k))))
    setBusy('')
    if (failed.length)
      window.alert(
        t('Teilweise fehlgeschlagen:') +
          '\n' +
          failed.map((a) => `${a}: ${st(res.errors[a]!)}`).join('\n'),
      )
  }

  const errorList = Object.entries(errors)

  return (
    <div className={shared.wrap}>
      <div className={shared.top}>
        <h2>{t('📧 E-MAILS')}</h2>
        {(filter.acc || filter.cat) && (
          <span
            className={s.chip}
            title={t('Filter aufheben')}
            onClick={() => setFilter({ acc: '', cat: '' })}
          >
            ✕ {filter.acc ? accName(filter.acc) : ''}
            {filter.acc && filter.cat ? ' · ' : ''}
            {filter.cat}
          </span>
        )}
        <span className={shared.spacer} />
        <button
          type="button"
          className={shared.tbtn}
          onClick={() => void refreshMailList(qc, true)}
        >
          {t('⟲ AKTUALISIEREN')}
        </button>
      </div>
      <div className={`${shared.top} ${s.bar}`}>
        <input
          className={s.search}
          placeholder={t('🔎 Suchen … (Absender, Betreff)')}
          value={filter.q}
          onChange={(e) => setFilter({ q: e.target.value })}
        />
        <span className={`${shared.vhint} ${s.count}`}>
          {list.length ? t('{n} Mails', { n: list.length }) : ''}
        </span>
        <button type="button" className={shared.tbtn} onClick={selectAll}>
          {allSel ? t('☒ KEINE MARKIEREN') : t('☑ ALLE MARKIEREN')}
        </button>
        {sel.size > 0 && (
          <select
            className={shared.msel}
            title={t('Markierte einer Kategorie zuweisen')}
            value="__none__"
            disabled={busy === 'cat'}
            onChange={(e) => {
              if (e.target.value !== '__none__') void catSelected(e.target.value)
            }}
          >
            <option value="__none__">{t('🏷 KATEGORIE …')}</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
            <option value="">{t('✕ Kategorie entfernen')}</option>
          </select>
        )}
        {sel.size > 0 && (
          <button
            type="button"
            className={`${shared.tbtn} ${shared.danger}`}
            disabled={busy === 'del'}
            onClick={() => void delSelected()}
          >
            {busy === 'del' ? t('🗑 LÖSCHE …') : t('🗑 LÖSCHEN ({n})', { n: sel.size })}
          </button>
        )}
      </div>
      {errorList.map(([a, e]) => (
        <div key={a} className={`${shared.err} ${s.errLine}`}>
          ⚠ <b>{a === FETCH_ERROR ? t('Abruf') : a}</b>: {st(e)}
        </div>
      ))}
      <div>
        {!list.length && (
          <div className={shared.vhint}>
            {accountsQ.isPending || (listQ.isFetching && !loaded)
              ? t('⟲ Lade E-Mails …')
              : loaded
                ? filter.acc || filter.cat || filter.q
                  ? t('Keine E-Mails (Filter aktiv).')
                  : t('Keine E-Mails.')
                : t('Noch nichts geladen.')}
          </div>
        )}
        {list.slice(0, limit).map((m) => (
          <Row
            key={mailKey(m)}
            m={m}
            on={sel.has(mailKey(m))}
            color={accColor(accounts, m.account)}
            date={fmtMailDate(m.ts, loc)}
            onToggle={(on) => toggle(mailKey(m), on)}
            onOpen={() => void nav(`/mail/msg?${new URLSearchParams(ref(m))}`)}
            onDelete={() => void delMail(m)}
          />
        ))}
        {list.length > limit && (
          <button
            type="button"
            className={`${shared.tbtn} ${s.more}`}
            onClick={() => setShown({ key: fkey, n: limit + CHUNK })}
          >
            {t('▼ WEITERE {n} ANZEIGEN ({shown} von {total})', {
              n: Math.min(CHUNK, list.length - limit),
              shown: limit,
              total: list.length,
            })}
          </button>
        )}
      </div>
    </div>
  )
}

const ref = (m: MailSummary) => ({ account: m.account, uid: m.uid, folder: m.folder || 'INBOX' })

interface RowProps {
  m: MailSummary
  on: boolean
  color: string
  date: string
  onToggle: (on: boolean) => void
  onOpen: () => void
  onDelete: () => void
}

function Row({ m, on, color, date, onToggle, onOpen, onDelete }: RowProps) {
  const { t } = useTranslation()
  return (
    <div
      className={`${s.row} ${m.seen ? '' : s.unread} ${on ? s.sel : ''}`}
      onClick={onOpen}
      data-testid="mail-row"
    >
      <input
        type="checkbox"
        className={s.chk}
        title={t('markieren')}
        checked={on}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => onToggle(e.target.checked)}
      />
      <span className={s.acc} style={{ borderColor: color, color }}>
        {accName(m.account)}
      </span>
      <div className={s.main}>
        <span className={s.from}>
          {m.seen ? '' : '● '}
          {m.from_name || m.from_addr || '?'}
        </span>
        <span className={s.sub}>{m.subject || t('(kein Betreff)')}</span>
      </div>
      {m.category && <span className={s.cat}>{m.category}</span>}
      <span className={s.date}>{date}</span>
      <span
        className={s.del}
        title={t('löschen (auch auf dem Server)')}
        onClick={(e) => {
          e.stopPropagation()
          onDelete()
        }}
      >
        🗑
      </span>
    </div>
  )
}
