import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate } from 'react-router'
import { errText, mailApi, type UploadedAttachment } from '@/api/mail'
import { fmtSize } from './format'
import { useMailStore } from './mailStore'
import { useMail, useServerText } from './useMail'
import shared from './shared.module.css'
import s from './MailCompose.module.css'

const MAX_UPLOAD = 25 * 1024 * 1024

/** Neue E-Mail / Antwort / Weiterleitung. Vorbelegung kommt aus dem Store. */
export function MailCompose() {
  const { t } = useTranslation()
  const st = useServerText()
  const nav = useNavigate()
  const { accounts, accountsQ } = useMail()
  // Nur beim Öffnen übernehmen — spätere Store-Änderungen dürfen nicht ins
  // halb getippte Formular fahren.
  const [pre] = useState(() => useMailStore.getState().draft)
  const froms = accounts.filter((a) => a.configured)
  const [from, setFrom] = useState(pre.from ?? '')
  const [to, setTo] = useState(pre.to ?? '')
  const [cc, setCc] = useState('')
  const [subject, setSubject] = useState(pre.subject ?? '')
  const [body, setBody] = useState(pre.body ?? '')
  const [atts, setAtts] = useState<UploadedAttachment[]>([])
  const [msg, setMsg] = useState<{ text: string; ok?: boolean }>({ text: '' })
  const [sending, setSending] = useState(false)
  const toRef = useRef<HTMLInputElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])

  if (accountsQ.isPending) return null
  // Ohne eingerichtetes Konto gibt es nichts zu senden → Konten einrichten.
  if (!froms.length) return <Navigate to="/mail/accounts" replace />
  const account = froms.some((a) => a.email === from) ? from : froms[0]!.email

  const upload = async (files: FileList | null) => {
    const added: UploadedAttachment[] = []
    for (const f of Array.from(files ?? [])) {
      if (f.size > MAX_UPLOAD) {
        window.alert(t('{name} ist zu groß (max. 25 MB)', { name: f.name }))
        continue
      }
      try {
        added.push(await mailApi.attach(f))
      } catch (e) {
        window.alert(st(errText(e)) || t('Upload fehlgeschlagen'))
      }
    }
    setAtts((cur) => [...cur, ...added])
  }

  const send = async () => {
    if (!to.trim()) {
      setMsg({ text: t('⚠ Empfänger fehlt') })
      toRef.current?.focus()
      return
    }
    setSending(true)
    setMsg({ text: t('⟲ sende …') })
    try {
      await mailApi.send({
        account,
        to: to.trim(),
        cc: cc.trim(),
        subject: subject.trim(),
        body,
        attachments: atts.map((a) => ({ path: a.path, name: a.name })),
        reply: pre.reply || '',
      })
      setMsg({ text: t('✅ gesendet!'), ok: true })
      timer.current = setTimeout(() => void nav('/mail'), 900)
    } catch (e) {
      setSending(false)
      setMsg({ text: '⚠ ' + st(errText(e)) })
    }
  }

  return (
    <div className={shared.wrap}>
      <div className={shared.top}>
        <button type="button" className={shared.backbtn} onClick={() => void nav('/mail')}>
          {t('← zurück')}
        </button>
        <h2 className={shared.small}>✉ {pre.reply ? t('ANTWORT') : t('NEUE E-MAIL')}</h2>
      </div>
      <div className={s.form}>
        <label htmlFor="mcFrom">{t('VON')}</label>
        <select
          id="mcFrom"
          className={`${shared.msel} ${s.from}`}
          value={account}
          onChange={(e) => setFrom(e.target.value)}
        >
          {froms.map((a) => (
            <option key={a.email}>{a.email}</option>
          ))}
        </select>
        <label htmlFor="mcTo">{t('AN')}</label>
        <input
          id="mcTo"
          ref={toRef}
          value={to}
          onChange={(e) => setTo(e.target.value)}
          placeholder={t('empfaenger@beispiel.de (mehrere mit Komma)')}
        />
        <label htmlFor="mcCc">{t('CC')}</label>
        <input
          id="mcCc"
          value={cc}
          onChange={(e) => setCc(e.target.value)}
          placeholder={t('(optional)')}
        />
        <label htmlFor="mcSub">{t('BETREFF')}</label>
        <input id="mcSub" value={subject} onChange={(e) => setSubject(e.target.value)} />
        <label htmlFor="mcBody">{t('NACHRICHT')}</label>
        <textarea id="mcBody" rows={12} value={body} onChange={(e) => setBody(e.target.value)} />
        <div>
          {atts.map((a, i) => (
            <span key={a.path} className={s.att}>
              📎 {a.name} <span className={s.dim}>({fmtSize(a.size || 0)})</span>
              <span className={s.x} onClick={() => setAtts((cur) => cur.filter((_, j) => j !== i))}>
                ✕
              </span>
            </span>
          ))}
        </div>
        <div className={s.actions}>
          <button type="button" className={shared.tbtn} onClick={() => fileRef.current?.click()}>
            {t('📎 ANHANG')}
          </button>
          <input
            ref={fileRef}
            type="file"
            multiple
            hidden
            data-testid="mc-file"
            onChange={(e) => {
              const files = e.target.files
              void upload(files).then(() => {
                // Gleiche Datei nochmal wählen können.
                e.target.value = ''
              })
            }}
          />
          <button
            type="button"
            className={`${shared.lgBtn} ${s.send}`}
            disabled={sending}
            onClick={() => void send()}
          >
            {t('➤ SENDEN')}
          </button>
          <span className={`${shared.vhint} ${msg.ok ? shared.ok : ''}`}>{msg.text}</span>
        </div>
      </div>
    </div>
  )
}
