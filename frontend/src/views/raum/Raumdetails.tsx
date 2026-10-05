import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStatus, useUsage, type UsageWindow } from '@/api/system'
import { locale } from '@/lib/i18n'
import { useSettings } from '@/stores/settings'
import { useSekunde } from '@/hooks/useSekunde'
import { parallelMatrix, type Viereck } from './kamera'
import { bcdSpalten, ZEILEN } from './binaer'
import {
  BINAER_MASS,
  KONTINGENT_MASS,
  REGAL_SCHILD,
  WAND_BINAER,
  WAND_KONTINGENT,
} from './stationen'
import s from './Raum.module.css'

// Kleine Dinge, die den Raum lebendig machen: an der Wand hängt eine Binäruhr,
// darunter steht, wie viel vom Claude-Kontingent schon verbraucht ist, und unter
// dem Regal, in welchem Projekt man gerade ist.

/** Die Binäruhr an der Wand: ein Gerät mit dunkler Glasfront, flach auf die Wand
 *  gelegt. Aus der Nähe (Uhr-Ansicht) zeigt sie Digital- und Tetris-Uhr. */
export function WandBinaeruhr({
  welt,
  weich = false,
}: {
  welt: { w: number; h: number }
  weich?: boolean
}) {
  const jetzt = useSekunde()
  if (!welt.w) return null
  const k = welt.w / 2048
  const [ol, or, ul] = WAND_BINAER.map(([x, y]) => [x * k, y * k] as const)
  const { w, h } = BINAER_MASS
  return (
    <div
      className={`${s.wandBinaer} ${weich ? s.weich : ''}`}
      style={{ width: w, height: h, transform: parallelMatrix(w, h, ol!, or!, ul!) }}
      aria-hidden
    >
      {bcdSpalten(jetzt).map((sp, i) => (
        <Fragment key={i}>
          {i > 0 && i % 2 === 0 && (
            <span className={`${s.wandTrenner} ${jetzt.getSeconds() % 2 ? s.binaerAus : ''}`}>
              <i />
              <i />
            </span>
          )}
          <span className={s.wandSpalte}>
            {ZEILEN.map((z) => (
              <i
                key={z}
                className={z >= 2 ** sp.bits ? s.binaerLeer : sp.wert & z ? s.binaerAn : ''}
              />
            ))}
          </span>
        </Fragment>
      ))}
    </div>
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

/** Wie viel vom Kontingent (5 Stunden, Woche) verbraucht ist, an der Wand
 *  unter der Uhr. Dieselben Zahlen wie oben in der Chat-Ansicht. Die Anzeige
 *  wird in festem Maß gezeichnet und als Ganzes auf die Wand gelegt — Schrift
 *  und Balken skalieren mit dem Raum. */
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
  const { w: kw, h: kh } = KONTINGENT_MASS
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
      style={{ width: kw, height: kh, transform: parallelMatrix(kw, kh, ol!, or!, ul!) }}
      aria-hidden
    >
      <span className={s.kontingentKopf}>{t('KONTINGENT')}</span>
      <div className={s.kontingentReihe}>
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
