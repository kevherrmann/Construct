import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import {
  attachmentUrl,
  errText,
  mailApi,
  patchMailList,
  useMailMessage,
  type MailRef,
} from '@/api/mail'
import { fmtSize, fwdSubject, mailSrcdoc, quote, replySubject } from './format'
import { useMailStore } from './mailStore'
import { useDeleteMail } from './useDeleteMail'
import { useLocale, useMail, useServerText } from './useMail'
import shared from './shared.module.css'
import s from './MailRead.module.css'

/** Eine Mail lesen: /mail/msg?account=…&uid=…&folder=… */
export function MailRead() {
  const { t } = useTranslation()
  const st = useServerText()
  const nav = useNavigate()
  const qc = useQueryClient()
  const loc = useLocale()
  const [params] = useSearchParams()
  const { categories, msgs } = useMail()
  const setDraft = useMailStore((x) => x.setDraft)
  const delMail = useDeleteMail()

  const r: MailRef | null = params.get('account')
    ? {
        account: params.get('account')!,
        uid: params.get('uid') ?? '',
        folder: params.get('folder') || 'INBOX',
      }
    : null
  const q = useMailMessage(r)
  const d = q.data
  const summary = r ? msgs.find((m) => m.account === r.account && m.uid === r.uid) : undefined

  // Der Server markiert beim Abruf als gelesen — die Liste zieht lokal nach.
  // Auch wenn die Liste erst NACH der Mail ankommt (direkt per URL geöffnet);
  // nur nicht, wenn gerade ✉ UNGELESEN geklickt wurde.
  const unread = useRef(false)
  const unseen = !!summary && !summary.seen
  useEffect(() => {
    if (!d || !unseen || unread.current) return
    patchMailList(qc, (ms) =>
      ms.map((m) => (m.account === d.account && m.uid === d.uid ? { ...m, seen: true } : m)),
    )
  }, [d, unseen, qc])

  // Ohne Angabe, welche Mail: zurück zur Liste statt einer leeren Seite.
  if (!r) return <Navigate to="/mail" replace />
  if (q.isPending) return <div className={shared.tool}>{t('⟲ Lade E-Mail …')}</div>
  if (q.isError || !d)
    return <div className={`${shared.err} ${s.loadErr}`}>⚠ {st(errText(q.error))}</div>

  const back = () => void nav('/mail')
  const when = d.ts ? new Date(d.ts * 1000).toLocaleString(loc) : ''
  const category = summary?.category ?? ''

  const setCategory = async (cat: string) => {
    try {
      await mailApi.categorize(d.key, cat)
    } catch (e) {
      window.alert(t('Kategorisieren fehlgeschlagen:') + ' ' + st(errText(e)))
      return
    }
    patchMailList(qc, (ms) =>
      ms.map((m) => (m.account === r.account && m.uid === r.uid ? { ...m, category: cat } : m)),
    )
  }

  const markUnread = async () => {
    unread.current = true
    try {
      await mailApi.flag(r, false)
    } catch {
      /* wie früher: trotzdem zurück zur Liste */
    }
    patchMailList(qc, (ms) =>
      ms.map((m) => (m.account === r.account && m.uid === r.uid ? { ...m, seen: false } : m)),
    )
    back()
  }

  const reply = () => {
    setDraft({
      from: r.account,
      to: d.from_addr,
      reply: d.message_id,
      subject: replySubject(d.subject),
      body:
        '\n\n' +
        t('Am {when} schrieb {who}:', { when, who: d.from_name || d.from_addr }) +
        '\n' +
        quote(d.text),
    })
    void nav('/mail/compose')
  }

  const forward = () => {
    setDraft({
      from: r.account,
      subject: fwdSubject(d.subject),
      body:
        '\n\n' +
        t('---------- Weitergeleitete Nachricht ----------') +
        `\n${t('Von:')} ${d.from_name || ''} <${d.from_addr || ''}>\n${t('Datum:')} ${when}\n${t('Betreff:')} ${d.subject || ''}\n\n` +
        (d.text || t('(HTML-Mail — Inhalt bitte manuell übernehmen)')),
    })
    void nav('/mail/compose')
  }

  return (
    <div className={shared.wrap}>
      <div className={shared.top}>
        <button type="button" className={shared.backbtn} onClick={back}>
          {t('← Posteingang')}
        </button>
        <button type="button" className={shared.tbtn} onClick={reply}>
          {t('↩ ANTWORTEN')}
        </button>
        <button type="button" className={shared.tbtn} onClick={forward}>
          {t('↪ WEITERLEITEN')}
        </button>
        <select
          className={shared.msel}
          title={t('Kategorie (nur lokal, nicht beim Anbieter)')}
          value={categories.includes(category) ? category : ''}
          onChange={(e) => void setCategory(e.target.value)}
        >
          <option value="">{t('— Kategorie —')}</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={shared.tbtn}
          title={t('als ungelesen markieren')}
          onClick={() => void markUnread()}
        >
          {t('✉ UNGELESEN')}
        </button>
        <button
          type="button"
          className={`${shared.tbtn} ${shared.danger}`}
          title={t('löschen (auch auf dem Server)')}
          onClick={async () => {
            if (await delMail({ ...r, subject: d.subject })) back()
          }}
        >
          🗑
        </button>
      </div>
      <div className={s.head}>
        <div className={s.sub}>{d.subject || t('(kein Betreff)')}</div>
        <div className={s.line}>
          {t('Von:')} <b>{d.from_name ? `${d.from_name} <${d.from_addr}>` : d.from_addr || '?'}</b>
        </div>
        <div className={s.line}>
          {t('An:')} {d.to || '—'}
          {d.cc ? ` · ${t('Cc:')} ${d.cc}` : ''}
        </div>
        <div className={s.line}>
          {when} · {t('Konto:')} {r.account}
        </div>
      </div>
      {d.attachments.length > 0 && (
        <div className={s.atts}>
          {d.attachments.map((a) => (
            <a key={a.idx} className={s.att} href={attachmentUrl(r, a.idx)}>
              📎 {a.name} <span className={s.dim}>({fmtSize(a.size || 0)})</span>
            </a>
          ))}
        </div>
      )}
      {d.html ? (
        // Keine Skripte (sandbox ohne allow-scripts)! Links gehen in ein neues
        // Fenster, das die Sandbox verlassen darf.
        <iframe
          className={s.frame}
          title={d.subject || 'mail'}
          sandbox="allow-popups allow-popups-to-escape-sandbox"
          srcDoc={mailSrcdoc(d.html)}
        />
      ) : (
        <div className={s.text}>{d.text || t('(kein Inhalt)')}</div>
      )}
    </div>
  )
}
