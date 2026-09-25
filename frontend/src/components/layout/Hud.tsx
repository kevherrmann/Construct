import { useTranslation } from 'react-i18next'
import { useAuthStatus, useUsage, type UsageWindow } from '@/api/system'
import { locale } from '@/lib/i18n'
import { useSettings } from '@/stores/settings'
import s from './Hud.module.css'

function UsageChip({ label, u }: { label: string; u?: UsageWindow }) {
  const { t } = useTranslation()
  const lang = useSettings((st) => st.boot.lang)
  if (!u || u.percent == null)
    return (
      <span className={s.chip} title={t('keine Daten')}>
        {label} —
      </span>
    )
  const p = Math.round(u.percent)
  const level = p >= 85 ? s.crit : p >= 60 ? s.warn : ''
  const title = u.resets_at
    ? t('Reset: {t} Uhr', {
        t: new Date(u.resets_at).toLocaleString(locale(lang), {
          weekday: 'short',
          hour: '2-digit',
          minute: '2-digit',
        }),
      })
    : undefined
  return (
    <span className={`${s.chip} ${level}`} title={title}>
      {label}
      <span className={s.bar}>
        <i style={{ width: `${Math.min(100, p)}%` }} />
      </span>
      <b>{p}%</b>
    </span>
  )
}

// Limits des Anthropic-Kontos und Anmeldestatus oben rechts.
export function Hud({ onAuthClick }: { onAuthClick?: () => void }) {
  const { t } = useTranslation()
  const lang = useSettings((st) => st.boot.lang)
  const auth = useAuthStatus()
  const hasClaude = auth.data?.cli !== false
  const usage = useUsage(hasClaude)

  let authChip
  if (auth.isError) authChip = { cls: s.crit, text: '🔑 ?', title: '' }
  else if (!auth.data) authChip = { cls: '', text: '🔑 …', title: t('Claude-Anmeldung') }
  // Kein Claude Code ist kein Fehler, sondern ein Zustand: wer nur über einen
  // externen Anbieter chattet, soll hier keinen Alarm sehen.
  else if (!auth.data.cli)
    authChip = {
      cls: '',
      text: t('🔑 OHNE CLAUDE'),
      title: t(
        'Claude Code ist nicht installiert — der Chat läuft über den Anbieter aus dem 🧠-Menü. Klicken für die Anleitung.',
      ),
    }
  else if (auth.data.ok)
    authChip = {
      cls: '',
      text: '🔑 OK',
      title:
        t('Angemeldet') +
        (auth.data.web_token
          ? t(' (Web-Login-Token)')
          : auth.data.env_token
            ? t(' (Server-Token)')
            : t(' (claudec-Login)')) +
        t(' — klicken zum Neu-Anmelden'),
    }
  else
    authChip = {
      cls: `${s.crit} ${s.alert}`,
      text: t('🔑 LOGIN NÖTIG'),
      title: t('Anmeldung abgelaufen — klicken zum Einloggen'),
    }

  const u = usage.data
  let limitChips = null
  // Die Limit-Chips zeigen Anthropic-Kontingente — ohne Claude sinnlos.
  if (hasClaude) {
    if (u?.limit_hit) {
      const until = new Date(u.limit_hit * 1000).toLocaleTimeString(locale(lang), {
        hour: '2-digit',
        minute: '2-digit',
      })
      limitChips = (
        <span className={`${s.chip} ${s.crit} ${s.alert}`} title={t('Nutzungs-Limit erreicht')}>
          {t('⛔ Limit — bis {t}', { t: until })}
        </span>
      )
    } else if (u && !u.available) {
      const title = t('Limits nicht abrufbar: {r}', { r: u.reason ?? '?' })
      limitChips = (
        <>
          <span className={s.chip} title={title}>
            5h —
          </span>
          <span className={s.chip} title={title}>
            {t('7T')} —
          </span>
        </>
      )
    } else
      limitChips = (
        <>
          <UsageChip label="5h" u={u?.five_hour} />
          <UsageChip label={t('7T')} u={u?.seven_day} />
        </>
      )
  }

  return (
    <span className={s.hud}>
      {limitChips}
      <button
        type="button"
        className={`${s.chip} ${s.click} ${authChip.cls}`}
        title={authChip.title}
        onClick={onAuthClick}
      >
        {authChip.text}
      </button>
    </span>
  )
}
