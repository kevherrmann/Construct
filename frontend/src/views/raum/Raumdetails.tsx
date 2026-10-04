import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStatus, useUsage, type UsageWindow } from '@/api/system'
import { locale } from '@/lib/i18n'
import { useSettings } from '@/stores/settings'
import { parallelMatrix, type Viereck } from './kamera'
import { REGAL_SCHILD, UHR_MATRIX, WAND_KONTINGENT } from './stationen'
import s from './Raum.module.css'

// Kleine Dinge, die den Raum lebendig machen: die Wanduhr geht richtig, unter
// dem Regal steht, in welchem Projekt man gerade ist, und neben der Uhr, wie
// viel vom Claude-Kontingent schon verbraucht ist.

/** Zeiger der Wanduhr, auf das gemalte Zifferblatt gelegt (Raumbild-Pixel). */
export function Wanduhr({ weich = false }: { weich?: boolean }) {
  const [jetzt, setJetzt] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setJetzt(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const sek = jetzt.getSeconds()
  const min = jetzt.getMinutes() + sek / 60
  const std = (jetzt.getHours() % 12) + min / 60
  // Zeiger im Einheitskreis, 12 Uhr = nach oben (y negativ)
  const zeiger = (grad: number, laenge: number, breite: number, cls: string) => (
    <line
      className={cls}
      x1={0}
      y1={0.14}
      x2={0}
      y2={-laenge}
      strokeWidth={breite}
      transform={`rotate(${grad})`}
    />
  )
  return (
    <svg
      className={`${s.uhr} ${weich ? s.weich : ''}`}
      viewBox="0 0 2048 1152"
      preserveAspectRatio="none"
      aria-hidden
    >
      <g transform={`matrix(${UHR_MATRIX.join(' ')})`}>
        {/* leichter Schatten, als lägen die Zeiger über dem Blatt */}
        <g transform="translate(0.035 0.05)" className={s.uhrSchatten}>
          {zeiger(std * 30, 0.5, 0.075, '')}
          {zeiger(min * 6, 0.76, 0.05, '')}
        </g>
        {zeiger(std * 30, 0.5, 0.075, s.uhrStunde!)}
        {zeiger(min * 6, 0.76, 0.05, s.uhrMinute!)}
        {zeiger(sek * 6, 0.84, 0.022, s.uhrSekunde!)}
        <circle r={0.055} className={s.uhrMitte} />
      </g>
    </svg>
  )
}

/** Der Projektname unter dem Regal, im Winkel der Regalfront. */
export function RegalSchild({
  name,
  welt,
  weich = false,
}: {
  name: string
  welt: { w: number; h: number }
  weich?: boolean
}) {
  const { t } = useTranslation()
  if (!welt.w || !name) return null
  const k = welt.w / 2048
  const [ol, or, ur, ul] = REGAL_SCHILD.map(
    ([x, y]) => [x * k, y * k] as const,
  ) as unknown as Viereck
  // Parallelogramm im Winkel der Regalfront; Höhe = Mittel aus links und rechts.
  const h = ((ul[1] - ol[1] + (ur[1] - or[1])) / 2) * 2
  const breite = Math.hypot(or[0] - ol[0], or[1] - ol[1]) * 2
  const schrift = Math.min(h * 0.56, breite / (name.length * 0.72 + 0.4))
  const unten: readonly [number, number] = [ol[0], ol[1] + h / 2]
  return (
    <div
      className={`${s.regalSchild} ${weich ? s.weich : ''}`}
      style={{ width: breite, height: h, transform: parallelMatrix(breite, h, ol, or, unten) }}
      title={name}
    >
      <span className={s.regalSchildKlein} style={{ fontSize: h * 0.17 }}>
        {t('PROJEKT')}
      </span>
      <span className={s.regalSchildName} style={{ fontSize: schrift }}>
        {name}
      </span>
    </div>
  )
}

// Die Anzeige wird in diesem festen Maß gezeichnet und dann als Ganzes auf die
// Wand gelegt — Schrift und Balken skalieren mit dem Raum.
const KW = 400
const KH = 320

/** Wie viel vom Kontingent (5 Stunden, Woche) verbraucht ist, an der Wand
 *  neben der Uhr. Dieselben Zahlen wie oben in der Chat-Ansicht. */
export function WandKontingent({
  welt,
  weich = false,
}: {
  welt: { w: number; h: number }
  weich?: boolean
}) {
  const { t } = useTranslation()
  const lang = useSettings((st) => st.boot.lang)
  const auth = useAuthStatus()
  const hatClaude = auth.data?.cli !== false
  const usage = useUsage(hatClaude)
  // Ohne Claude Code gibt es kein Anthropic-Kontingent, also auch keine Anzeige.
  if (!welt.w || !hatClaude) return null
  const k = welt.w / 2048
  const [ol, or, ul] = WAND_KONTINGENT.map(([x, y]) => [x * k, y * k] as const)
  const u = usage.data
  const zeit = (iso: string | null | undefined, mitTag: boolean) =>
    iso
      ? new Date(iso).toLocaleString(locale(lang), {
          ...(mitTag ? { weekday: 'short' } : {}),
          hour: '2-digit',
          minute: '2-digit',
        })
      : ''
  const sperreBis = u?.limit_hit
    ? new Date(u.limit_hit * 1000).toLocaleTimeString(locale(lang), {
        hour: '2-digit',
        minute: '2-digit',
      })
    : null
  return (
    <div
      className={`${s.kontingent} ${weich ? s.weich : ''}`}
      style={{ width: KW, height: KH, transform: parallelMatrix(KW, KH, ol!, or!, ul!) }}
      aria-hidden
    >
      <span className={s.kontingentKopf}>{t('KONTINGENT')}</span>
      {sperreBis ? (
        <div className={`${s.kontingentZeile} ${s.kontingentKrit}`}>
          <b>{t('LIMIT')}</b>
          <span className={s.kontingentLimit}>{t('bis {t}', { t: sperreBis })}</span>
        </div>
      ) : (
        <KontingentZeile
          name={t('5 STD')}
          u={u?.five_hour}
          reset={zeit(u?.five_hour?.resets_at, false)}
        />
      )}
      <KontingentZeile
        name={t('WOCHE')}
        u={u?.seven_day}
        reset={zeit(u?.seven_day?.resets_at, true)}
      />
    </div>
  )
}

function KontingentZeile({ name, u, reset }: { name: string; u?: UsageWindow; reset: string }) {
  const { t } = useTranslation()
  const p = u?.percent == null ? null : Math.round(u.percent)
  const stufe = p == null ? '' : p >= 85 ? s.kontingentKrit : p >= 60 ? s.kontingentWarn : ''
  return (
    <div className={`${s.kontingentZeile} ${stufe}`}>
      <b>{name}</b>
      <span className={s.kontingentWert}>{p == null ? '—' : `${p}%`}</span>
      <span className={s.kontingentBalken}>
        <i style={{ width: `${Math.min(100, p ?? 0)}%` }} />
      </span>
      <span className={s.kontingentReset}>{reset && t('Reset {t}', { t: reset })}</span>
    </div>
  )
}
