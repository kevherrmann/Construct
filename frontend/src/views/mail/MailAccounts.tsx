import { useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Trans, useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import {
  MAIL_KEYS,
  errText,
  mailApi,
  needsServer,
  patchMailList,
  type MailAccount,
  type MailServerInput,
} from '@/api/mail'
import { accColor } from './format'
import { useMsLogin } from './msLogin'
import { useMail, useServerText } from './useMail'
import shared from './shared.module.css'
import s from './MailAccounts.module.css'

type Status = { node: ReactNode; ok?: boolean }

const NO_SERVER: MailServerInput = {
  imap_host: '',
  imap_port: '993',
  smtp_host: '',
  smtp_port: '465',
  user: '',
}

// Woher die Server eines Kontos stammen (mail.detect()) — für die Zeile unter dem Hinweis.
const SOURCE: Record<string, string> = {
  Adresse: 'bekannter Anbieter',
  MX: 'erkannt über den MX-Eintrag',
  'Thunderbird-Datenbank': 'aus der Thunderbird-Datenbank',
  Autoconfig: 'aus der Autoconfig der Domain',
  'von Hand': 'von Hand eingetragen',
}

/**
 * Konten verwalten: /mail/accounts. Auch das Ziel des Links aus
 * ⚙ Einstellungen → E-Mail-Konten.
 */
export function MailAccounts() {
  const { t } = useTranslation()
  const st = useServerText()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { accounts } = useMail()
  const [status, setStatus] = useState<Record<string, Status>>({})
  const [pw, setPw] = useState<Record<string, string>>({})
  const [newEmail, setNewEmail] = useState('')
  const [newPw, setNewPw] = useState('')
  const [newMsg, setNewMsg] = useState<Status | null>(null)
  // Serverfelder: null = zu. Gehen auf, wenn die Erkennung nichts findet
  // oder man sie selbst aufklappt.
  const [srv, setSrv] = useState<MailServerInput | null>(null)
  const [adding, setAdding] = useState(false)
  const ms = useMsLogin((x) => x.byAccount)

  // Eigene Aktion auf der Seite ersetzt eine ältere Microsoft-Meldung.
  const setSt = (em: string, node: ReactNode, ok?: boolean) => {
    useMsLogin.getState().clear(em)
    setStatus((cur) => ({ ...cur, [em]: { node, ok } }))
  }
  const reloadAccounts = () => qc.invalidateQueries({ queryKey: MAIL_KEYS.accounts })
  // Nach erfolgreichem Test die Liste nur als veraltet markieren — neu geladen
  // wird beim Zurück zum Posteingang (alte Oberfläche: mailLoaded=false).
  // Sofort alles neu zu holen ließe Zähler in der Seitenleiste verschwinden.
  const reloadList = () =>
    void qc.invalidateQueries({ queryKey: MAIL_KEYS.list, refetchType: 'none' })

  const save = async (em: string) => {
    const p = pw[em] ?? ''
    if (!p) return setSt(em, t('⚠ Passwort eingeben'))
    setSt(em, t('⟲ speichere …'))
    try {
      await mailApi.saveAccount(em, p)
    } catch (e) {
      return setSt(em, '⚠ ' + st(errText(e)))
    }
    setSt(em, t('✓ gespeichert — jetzt TEST klicken'), true)
    await reloadAccounts()
  }

  const test = async (em: string) => {
    setSt(em, t('⟲ teste Login + Posteingang …'))
    try {
      const j = await mailApi.test(em)
      setSt(em, t('✅ funktioniert — {n} Mails im Posteingang', { n: j.inbox }), true)
      reloadList()
    } catch (e) {
      setSt(em, '⚠ ' + st(errText(e)))
    }
  }

  const msLogin = async (em: string) => {
    setSt(em, t('⟲ starte Microsoft-Login …'))
    let j
    try {
      j = await mailApi.msLogin(em)
    } catch (e) {
      return setSt(em, '⚠ ' + st(errText(e)))
    }
    setStatus((cur) => {
      const next = { ...cur }
      delete next[em]
      return next
    })
    useMsLogin.getState().start(em, j.url, j.code)
  }

  const remove = async (em: string) => {
    if (
      !window.confirm(
        t('Konto „{em}“ aus CONSTRUCT entfernen?', { em }) +
          '\n\n' +
          t(
            '(Das Postfach selbst bleibt natürlich bestehen — es wird nur hier nicht mehr abgerufen.)',
          ),
      )
    )
      return
    try {
      await mailApi.deleteAccount(em)
    } catch (e) {
      window.alert('⚠ ' + st(errText(e)))
    }
    patchMailList(qc, (ms) => ms.filter((m) => m.account !== em))
    await reloadAccounts()
  }

  const add = async () => {
    const em = newEmail.trim()
    if (!em) return setNewMsg({ node: t('⚠ Adresse fehlt') })
    // Die Erkennung fragt DNS und die Thunderbird-Datenbank — das dauert einen Moment.
    setNewMsg({ node: srv ? t('⟲ speichere …') : t('⟲ suche die Mail-Server …') })
    setAdding(true)
    let r
    try {
      r = await mailApi.saveAccount(em, newPw, srv ?? undefined)
    } catch (e) {
      if (needsServer(e)) setSrv((cur) => cur ?? { ...NO_SERVER })
      return setNewMsg({ node: '⚠ ' + st(errText(e)) })
    } finally {
      setAdding(false)
    }
    setNewEmail('')
    setNewPw('')
    setSrv(null)
    setNewMsg(
      r && r.provider
        ? {
            node: t('✓ {em}: {provider}', { em: em.toLowerCase(), provider: r.provider }),
            ok: true,
          }
        : null,
    )
    await reloadAccounts()
  }

  const srcText = (src?: string) => {
    const k = src ? SOURCE[src] : undefined
    return k ? ` · ${t(k)}` : ''
  }

  const srvField = (k: keyof MailServerInput, placeholder: string, port?: boolean) => (
    <input
      className={port ? s.port : undefined}
      value={srv?.[k] ?? ''}
      aria-label={placeholder}
      onChange={(e) => setSrv((cur) => ({ ...(cur ?? NO_SERVER), [k]: e.target.value }))}
      placeholder={placeholder}
      inputMode={port ? 'numeric' : undefined}
    />
  )

  const stEl = (a: MailAccount, grow?: boolean) => {
    const m = ms[a.email]
    // Microsoft-Anmeldung läuft (oder lief) im Hintergrund weiter — ihr Stand
    // steht darum im eigenen Store, nicht im Zustand dieser Seite.
    const x: Status | undefined = m
      ? m.phase === 'wait'
        ? {
            node: (
              <Trans
                i18nKey="1. <a>{url}</a> öffnen  ·  2. Code <b>{code}</b> eingeben  ·  ⟲ warte auf Bestätigung …"
                values={{ url: m.url, code: m.code }}
                components={{
                  a: (
                    <a href={m.url} target="_blank" rel="noopener noreferrer" className={s.link} />
                  ),
                  b: <b className={s.code} />,
                }}
              />
            ),
          }
        : m.phase === 'ok'
          ? { node: t('✅ verbunden!'), ok: true }
          : { node: '⚠ ' + st(m.message) }
      : status[a.email]
    return (
      <span
        className={`${shared.vhint} ${x?.ok ? shared.ok : ''}`}
        style={grow ? { flex: 1 } : undefined}
        data-testid={`st-${a.email}`}
      >
        {x?.node}
      </span>
    )
  }

  return (
    <div className={shared.wrap}>
      <div className={shared.top}>
        <button type="button" className={shared.backbtn} onClick={() => void nav('/mail')}>
          {t('← Posteingang')}
        </button>
        <h2 className={shared.small}>{t('⚙ E-MAIL-KONTEN')}</h2>
      </div>
      {accounts.map((a) => (
        <div key={a.email} className={s.acc}>
          <div className={s.head}>
            <span
              className={shared.mdot}
              style={{ background: a.configured ? accColor(accounts, a.email) : '#444' }}
            />
            <b>{a.email}</b>
            <span className={s.prov}>{a.provider}</span>
            <span className={s.st}>
              {a.configured ? t('✓ eingerichtet') : t('— noch nicht eingerichtet')}
            </span>
            <span
              className={s.mx}
              title={t('Konto aus der Liste entfernen')}
              onClick={() => void remove(a.email)}
            >
              ✕
            </span>
          </div>
          <div className={`${shared.vhint} ${s.hint}`}>{st(a.hint || '')}</div>
          {a.imap && a.smtp && (
            <div className={`${shared.vhint} ${s.servers}`}>
              IMAP {a.imap} · SMTP {a.smtp}
              {srcText(a.source)}
            </div>
          )}
          {a.auth === 'oauth' ? (
            <div className={s.row}>
              <button type="button" className={shared.tbtn} onClick={() => void msLogin(a.email)}>
                {t('🔑 MICROSOFT-LOGIN')}
              </button>
              <button type="button" className={shared.tbtn} onClick={() => void test(a.email)}>
                {t('TEST')}
              </button>
              {stEl(a, true)}
            </div>
          ) : (
            <div className={s.row}>
              <input
                type="password"
                autoComplete="new-password"
                aria-label={a.email}
                value={pw[a.email] ?? ''}
                onChange={(e) => setPw((cur) => ({ ...cur, [a.email]: e.target.value }))}
                placeholder={
                  a.configured
                    ? t('••••••••  (gespeichert — nur zum Ändern neu eingeben)')
                    : t('Passwort / App-Passwort')
                }
              />
              <button type="button" className={shared.tbtn} onClick={() => void save(a.email)}>
                {t('SPEICHERN')}
              </button>
              <button type="button" className={shared.tbtn} onClick={() => void test(a.email)}>
                {t('TEST')}
              </button>
              {stEl(a)}
            </div>
          )}
        </div>
      ))}
      <div className={s.acc}>
        <b className={s.addTitle}>{t('＋ Konto hinzufügen')}</b>
        <div className={s.row}>
          <input
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder={t('neue@adresse.de')}
          />
          <input
            type="password"
            autoComplete="new-password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            placeholder={t('Passwort (bei Outlook/Microsoft 365 leer lassen)')}
          />
          <button
            type="button"
            className={shared.tbtn}
            disabled={adding}
            onClick={() => void add()}
          >
            {t('HINZUFÜGEN')}
          </button>
        </div>
        {srv && (
          <>
            <div className={s.row}>
              {srvField('imap_host', t('IMAP-Server, z. B. imap.firma.de'))}
              {srvField('imap_port', t('Port'), true)}
              {srvField('smtp_host', t('SMTP-Server, z. B. smtp.firma.de'))}
              {srvField('smtp_port', t('Port'), true)}
            </div>
            <div className={s.row}>{srvField('user', t('Benutzername (leer = die Adresse)'))}</div>
            <div className={`${shared.vhint} ${s.hint}`}>
              {t(
                'Die Angaben stehen in der Hilfe deines Mail-Anbieters. Port 993 bzw. 465 heißt SSL, alle anderen STARTTLS. Unverschlüsselt geht nicht.',
              )}
            </div>
          </>
        )}
        <div className={s.row}>
          <button
            type="button"
            className={s.toggle}
            onClick={() => setSrv((cur) => (cur ? null : { ...NO_SERVER }))}
          >
            {srv ? t('▾ Server automatisch suchen') : t('▸ Server selbst eintragen')}
          </button>
          <span className={`${shared.vhint} ${newMsg?.ok ? shared.ok : ''}`}>{newMsg?.node}</span>
        </div>
        <div className={`${shared.vhint} ${s.hint}`}>
          {t(
            'Für eigene Domains (info@firma.de) sucht CONSTRUCT die Server selbst: über den MX-Eintrag der Domain und die Datenbank von Thunderbird.',
          )}
        </div>
      </div>
      <div className={`${shared.vhint} ${s.foot}`}>
        {t('🔒 Zugangsdaten liegen nur auf deinem Server in')} <code>.mail-accounts.json</code>{' '}
        {t('(chmod 600) — sie tauchen nie im Browser auf.')}
        <br />
        {t(
          '🏷 Kategorien existieren nur hier im Chat — auf den Mail-Servern ändert sich dadurch nichts. Gelöschte Mails wandern dagegen echt in den Server-Papierkorb.',
        )}
      </div>
    </div>
  )
}
