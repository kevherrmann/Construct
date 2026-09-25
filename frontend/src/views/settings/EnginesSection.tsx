import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { installState, startInstall, useEngines, type Engine } from '@/api/settings'
import { refreshProviders } from '@/api/providers'
import { useAuthStatus } from '@/api/system'
import { usePolling } from '@/hooks/usePolling'
import { rich } from '@/lib/rich'
import { trServer } from '@/lib/serverText'
import { openClaudeAuth, openDialog } from '@/stores/dialogs'
import { useSettings } from '@/stores/settings'
import { LogBox, Note, Section } from './parts'
import s from './Settings.module.css'

// Zwei Wege zu Werkzeugen: Claude Code (Anthropic-Konto) und Hermes (alles
// andere). Beide lassen sich hier installieren, statt den Nutzer ins Terminal
// zu schicken — dasselbe Muster wie beim Ollama-Download: anstoßen, pollen.
function useInstall(which: Engine) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [running, setRunning] = useState(false)
  const [log, setLog] = useState<string[] | null>(null)
  const [note, setNote] = useState('')

  usePolling(
    running,
    () => installState(which),
    (st) => {
      setLog(st.log ?? [])
      if (!st.done) return
      setRunning(false)
      setNote(st.error ? '⚠ ' + trServer(st.error) : t('✓ fertig'))
      void qc.invalidateQueries({ queryKey: ['engines'] })
      if (which === 'claude') void qc.invalidateQueries({ queryKey: ['auth-status'] })
      // Modell-Liste neu holen: mit Hermes stehen jetzt andere Wege offen.
      void refreshProviders(qc)
    },
  )

  const start = async () => {
    setRunning(true)
    setLog([])
    setNote('')
    await startInstall(which).catch(() => undefined)
  }
  return { running, log, note, start }
}

export function EnginesSection() {
  const { t } = useTranslation()
  const boot = useSettings((st) => st.boot)
  const auth = useAuthStatus()
  const eng = useEngines()
  const claude = useInstall('claude')
  const hermes = useInstall('hermes')

  const hasClaude = auth.data ? auth.data.cli !== false : boot.claude
  const webLogin = auth.data ? auth.data.can_web_login : boot.web_login
  const c = eng.data?.claude
  const h = eng.data?.hermes

  const claudeBtn = () =>
    // Ohne Pseudo-Terminal (Windows) oder ohne Claude Code: Anleitung statt Login.
    openClaudeAuth({ cli: hasClaude, can_web_login: webLogin })

  return (
    <Section id="modelle">
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.head}>
            <h4>1 · Claude Code</h4>
            {hasClaude ? (
              <span className={`${s.tag} ${s.ok}`}>{t('INSTALLIERT')}</span>
            ) : (
              <span className={`${s.tag} ${s.warn}`}>{t('NICHT INSTALLIERT')}</span>
            )}
          </span>
          <span className={s.d}>
            {rich(
              t(
                'Läuft über dein <b>Anthropic-Abo</b> (OAuth) oder einen API-Key. Der einzige Weg mit <b>echtem Zugriff</b> auf Dateien und Terminal — hier greifen 📂 Ordner und 🛡 Modus. Ein Schlüssel von einem anderen Anbieter funktioniert dafür nicht.',
              ),
            )}
          </span>
          <span className={s.actions}>
            <button type="button" className={s.btn} onClick={claudeBtn}>
              {hasClaude ? t('🔑 Anmeldung') : t('📋 Anleitung')}
            </button>
            {c && !c.installed && (
              <button
                type="button"
                className={s.btn}
                disabled={claude.running || !c.npm}
                onClick={() => void claude.start()}
              >
                {!c.npm
                  ? t('braucht Node.js (nodejs.org)')
                  : claude.running
                    ? t('läuft…')
                    : t('Installieren')}
              </button>
            )}
            <Note text={claude.note} />
          </span>
          {claude.log && <LogBox lines={claude.log} />}
        </span>
      </div>

      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.head}>
            <h4>{t('2 · Fremde Anbieter')}</h4>
            <span className={s.tag}>{t('ÜBER HERMES')}</span>
          </span>
          <span className={s.d}>
            {rich(
              t(
                'ChatGPT, Gemini, DeepSeek, lokale Ollama-Modelle oder jede OpenAI-kompatible API. Diese Modelle laufen über <b>Hermes</b> (Punkt 3) und können damit ebenfalls Dateien und Terminal. Schlüssel bleiben lokal in <code>.llm-config.json</code>.<br>Angezeigt werden nur Modelle, die <b>Werkzeug-Aufrufe beherrschen</b> — ohne die würde der Agent seine Befehle als Fließtext ausgeben, statt sie auszuführen.',
              ),
            )}
          </span>
          <span className={s.actions}>
            <button type="button" className={s.btn} onClick={() => openDialog('providers')}>
              {t('⚙ Anbieter einrichten…')}
            </button>
          </span>
        </span>
      </div>

      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.head}>
            <h4>3 · Hermes</h4>
            {!h ? (
              <span className={s.tag}>…</span>
            ) : h.installed ? (
              <span className={`${s.tag} ${s.ok}`} title={`${h.version || ''}\n${h.home || ''}`}>
                {t('INSTALLIERT')}
              </span>
            ) : (
              <span className={`${s.tag} ${s.warn}`}>{t('NICHT INSTALLIERT')}</span>
            )}
          </span>
          <span className={s.d}>
            {rich(
              t(
                'Fährt die <b>Chat-Anbieter von oben mit Werkzeugen</b> — Dateien und Terminal ohne Anthropic-Konto, auch mit lokalen Modellen über Ollama. Ohne Hermes lassen sich fremde Modelle nicht nutzen.',
              ),
            )}
          </span>
          <span className={s.actions}>
            {!h?.installed && (
              <button
                type="button"
                className={s.btn}
                disabled={hermes.running || (h && !h.posix)}
                onClick={() => void hermes.start()}
              >
                {h && !h.posix
                  ? t('nur Linux / macOS')
                  : hermes.running
                    ? t('läuft…')
                    : t('Installieren')}
              </button>
            )}
            <Note text={hermes.note} />
          </span>
          {hermes.log && <LogBox lines={hermes.log} />}
        </span>
      </div>
    </Section>
  )
}
