import { trServer } from '@/lib/serverText'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { MAIL_KEYS, mailApi, patchMailList } from '@/api/mail'
import { accColor, accName } from './format'
import { useMailStore } from './mailStore'
import { useMail } from './useMail'
import shared from './shared.module.css'
import s from './MailSide.module.css'

/** Seitenleiste: Konten, Kategorien, Neue E-Mail, Konten verwalten. */
export function MailSide() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { accounts, categories, msgs, errors } = useMail()
  const filter = useMailStore((st) => st.filter)
  const setFilter = useMailStore((st) => st.setFilter)
  const setDraft = useMailStore((st) => st.setDraft)

  const unreadAll = msgs.filter((m) => !m.seen).length
  const uncat = msgs.filter((m) => !m.category).length

  // Filter wählen zeigt immer die Liste — auch aus einer offenen Mail heraus.
  const pick = (f: { acc?: string; cat?: string }) => {
    setFilter(f)
    void nav('/mail')
  }

  const addCat = async () => {
    const n = window.prompt(t('Name der neuen Kategorie:'))
    if (!n || !n.trim()) return
    try {
      const r = await mailApi.editCategories({ add: n.trim() })
      qc.setQueryData(MAIL_KEYS.categories, r.categories)
    } catch {
      void qc.invalidateQueries({ queryKey: MAIL_KEYS.categories })
    }
  }

  const delCat = async (c: string) => {
    if (
      !window.confirm(
        t('Kategorie „{c}“ löschen? (Die E-Mails bleiben natürlich erhalten.)', { c }),
      )
    )
      return
    try {
      const r = await mailApi.editCategories({ remove: c })
      qc.setQueryData(MAIL_KEYS.categories, r.categories)
    } catch {
      void qc.invalidateQueries({ queryKey: MAIL_KEYS.categories })
    }
    if (filter.cat === c) setFilter({ cat: '' })
    patchMailList(qc, (ms) => ms.map((m) => (m.category === c ? { ...m, category: '' } : m)))
  }

  return (
    <div className={s.side}>
      <button
        type="button"
        className={s.add}
        onClick={() => {
          setDraft({})
          void nav('/mail/compose')
        }}
      >
        {t('✉ NEUE E-MAIL')}
      </button>
      <div className={s.uh}>{t('KONTEN')}</div>
      <div className={`${s.item} ${!filter.acc ? s.on : ''}`} onClick={() => pick({ acc: '' })}>
        📥 <span className={s.mn}>{t('Alle Postfächer')}</span>
        {unreadAll > 0 && <span className={s.fc}>{unreadAll}</span>}
      </div>
      {accounts.map((a) => {
        const unread = msgs.filter((m) => m.account === a.email && !m.seen).length
        const err = errors[a.email]
        const color = accColor(accounts, a.email)
        return (
          <div
            key={a.email}
            className={`${s.item} ${filter.acc === a.email ? s.on : ''}`}
            title={err ? trServer(err) : a.email}
            onClick={() => pick({ acc: a.email })}
          >
            <span
              className={shared.mdot}
              style={{
                background: a.configured ? (err ? '#ff5c5c' : color) : '#444',
                boxShadow: `0 0 6px ${a.configured && !err ? color : 'transparent'}`,
              }}
            />
            <span className={s.mn}>
              {accName(a.email)}
              {err ? ' ⚠' : ''}
            </span>
            {unread > 0 && <span className={s.fc}>{unread}</span>}
          </div>
        )
      })}
      <div className={s.uh}>
        {t('KATEGORIEN')}{' '}
        <span
          className={s.catAdd}
          title={t('Neue Kategorie anlegen')}
          onClick={() => void addCat()}
        >
          ＋
        </span>
      </div>
      <div
        className={`${s.item} ${!filter.cat ? s.on : ''}`}
        title={t('Alles ohne Kategorie')}
        onClick={() => pick({ cat: '' })}
      >
        ▤ <span className={s.mn}>{t('Posteingang')}</span>
        {uncat > 0 && <span className={s.fc}>{uncat}</span>}
      </div>
      {categories.map((c) => {
        const n = msgs.filter((m) => m.category === c).length
        return (
          <div
            key={c}
            className={`${s.item} ${filter.cat === c ? s.on : ''}`}
            onClick={() => pick({ cat: c })}
          >
            <span className={s.mn}>{c}</span>
            {n > 0 && <span className={s.fc}>{n}</span>}
            <span
              className={s.mx}
              title={t('Kategorie löschen')}
              onClick={(e) => {
                e.stopPropagation()
                void delCat(c)
              }}
            >
              ✕
            </span>
          </div>
        )
      })}
      <button
        type="button"
        className={`${s.add} ${s.cfg}`}
        onClick={() => void nav('/mail/accounts')}
      >
        {t('⚙ KONTEN VERWALTEN')}
      </button>
    </div>
  )
}
