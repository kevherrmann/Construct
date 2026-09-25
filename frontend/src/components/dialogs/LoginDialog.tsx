import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { startLogin, submitLoginCode } from '@/api/auth'
import { useAuthStatus } from '@/api/system'
import { trServer } from '@/lib/serverText'
import { rich } from '@/lib/rich'
import { useDialogs } from '@/stores/dialogs'
import { useSettings } from '@/stores/settings'
import { Dialog } from './Dialog'
import s from './LoginDialog.module.css'

type Msg = { cls: '' | 'ok' | 'bad'; text: string }

// Claude-Login über die Web-UI: `claude setup-token` läuft am Server in einem
// Pseudo-Terminal; hier nur URL anzeigen und den Code zurückreichen.
function LoginBody({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [url, setUrl] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [msg, setMsg] = useState<Msg>({ cls: '', text: '' })
  const codeRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (url) codeRef.current?.focus()
  }, [url])

  useEffect(() => {
    if (!done) return
    const id = setTimeout(onClose, 2500)
    return () => clearTimeout(id)
  }, [done, onClose])

  const start = async () => {
    setBusy(true)
    setMsg({ cls: '', text: t('⟲ starte Login … (kann ein paar Sekunden dauern)') })
    try {
      const j = await startLogin()
      if (!j.url) throw new Error('?')
      setUrl(j.url)
      setMsg({ cls: '', text: '' })
    } catch (e) {
      setMsg({ cls: 'bad', text: '⚠ ' + trServer((e as Error).message) })
    }
    setBusy(false)
  }

  const send = async () => {
    const c = code.trim()
    if (!c) return
    setBusy(true)
    setMsg({ cls: '', text: t('⟲ prüfe Code …') })
    try {
      await submitLoginCode(c)
      setMsg({
        cls: 'ok',
        text: t(
          '✅ Angemeldet! CONSTRUCT läuft jetzt mit einem langlebigen Token — kein Terminal-Login mehr nötig.',
        ),
      })
      setDone(true)
      void qc.invalidateQueries({ queryKey: ['auth-status'] })
      void qc.invalidateQueries({ queryKey: ['usage'] })
    } catch (e) {
      setMsg({ cls: 'bad', text: '⚠ ' + trServer((e as Error).message) })
      setBusy(false)
    }
  }

  return (
    <>
      <p style={{ opacity: 0.85 }}>
        {t(
          'Meldet Cody bei deiner Claude-Subscription an — direkt hier, ohne Terminal. Es wird ein langlebiger Token erzeugt, der auch nach Ablauf des normalen Logins weiter funktioniert.',
        )}
      </p>
      {!url && (
        <div className={s.step}>
          <button type="button" className={s.btn} disabled={busy} onClick={start}>
            {t('LOGIN STARTEN')}
          </button>
        </div>
      )}
      {url && !done && (
        <div className={s.step}>
          <p>
            <b>1.</b> {t('Diesen Link öffnen und mit deinem Claude-Konto anmelden:')}
          </p>
          <p>
            <a href={url} target="_blank" rel="noopener noreferrer">
              {url}
            </a>
          </p>
          <p>
            <b>2.</b> {t('Den Code, den dir die Seite zeigt, hier einfügen:')}
          </p>
          <input
            ref={codeRef}
            className={s.input}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                void send()
              }
            }}
            placeholder={t('Code hier einfügen')}
            autoComplete="off"
            spellCheck={false}
          />
          <button type="button" className={s.btn} disabled={busy} onClick={send}>
            {t('CODE BESTÄTIGEN')}
          </button>
        </div>
      )}
      <div className={`${s.msg} ${msg.cls ? s[msg.cls] : ''}`}>{msg.text}</div>
    </>
  )
}

export function LoginDialog() {
  const open = useDialogs((d) => d.current === 'login')
  const close = useDialogs((d) => d.close)
  return (
    <Dialog open={open} onClose={close} title="🔑 CLAUDE LOGIN">
      {/* Radix hängt den Inhalt beim Schließen aus — jedes Öffnen beginnt also
          frisch bei Schritt 1 mit leerem Feld, wie in der alten Oberfläche. */}
      <LoginBody onClose={close} />
    </Dialog>
  )
}

// Anleitung, wenn der Web-Login nicht geht: Claude Code fehlt, oder Windows
// (kein Pseudo-Terminal). In der alten Oberfläche stand das als Systemnotiz
// im Chat; hier als eigene Box, damit es von überall aus erreichbar ist.
export function ClaudeSetupDialog() {
  const { t } = useTranslation()
  const boot = useSettings((st) => st.boot)
  const auth = useAuthStatus()
  const hasClaude = auth.data ? auth.data.cli !== false : boot.claude
  const webLogin = auth.data ? auth.data.can_web_login : boot.web_login
  const open = useDialogs((d) => d.current === 'claude')
  const close = useDialogs((d) => d.close)
  return (
    <Dialog open={open} onClose={close} title="🔑 CLAUDE CODE">
      <p>
        {hasClaude ? (
          t('Claude Code ist installiert.')
        ) : (
          <>
            {rich(
              t(
                'Claude Code ist auf diesem Rechner <b>nicht installiert</b>. Ohne das läuft der Chat über den Anbieter aus dem 🧠-Menü (ChatGPT, Gemini …) — das reicht zum Reden, aber nicht für Dateien und Terminal.',
              ),
            )}
          </>
        )}
      </p>
      {!hasClaude && (
        <p>
          {t('Nachinstallieren (braucht Node.js):')}
          <br />
          <code>npm install -g @anthropic-ai/claude-code</code>
        </p>
      )}
      <p>
        {webLogin
          ? t('Anmelden geht danach direkt hier über diesen Knopf.')
          : rich(
              t(
                'Anmelden danach <b>einmal im Terminal</b>: <code>claude</code> eingeben und dem Login folgen. CONSTRUCT erkennt die Anmeldung anschließend von selbst — der Login-Dialog in der Oberfläche braucht ein Pseudo-Terminal, das es unter Windows nicht gibt.',
              ),
            )}
      </p>
      <p style={{ opacity: 0.7 }}>
        {t('Dafür braucht es ein Anthropic-Konto (Abo oder API-Guthaben).')}
      </p>
    </Dialog>
  )
}
