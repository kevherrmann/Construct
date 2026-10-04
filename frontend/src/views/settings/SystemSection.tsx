import { useTranslation } from 'react-i18next'
import { istLokal } from '@/api/system'
import { BeendenKnopf } from '@/components/layout/Beenden'
import { Section } from './parts'
import s from './Settings.module.css'

/** CONSTRUCT beenden — dasselbe wie ⏻ oben rechts, hier mit Erklärung. */
export function BeendenSection() {
  const { t } = useTranslation()
  return (
    <Section id="beenden">
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.d}>
            {istLokal()
              ? t(
                  'Das Fenster zu schließen beendet CONSTRUCT nicht: der Server läuft weiter, damit Telegram-Bot und geplante Aufgaben funktionieren. Hier (oder mit ⏻ oben rechts) fährst du ihn ganz herunter.',
                )
              : t('Beenden geht nur am Rechner, auf dem CONSTRUCT läuft.')}
          </span>
          <span className={s.actions}>
            <BeendenKnopf className={s.btn} mitText />
          </span>
        </span>
      </div>
    </Section>
  )
}
