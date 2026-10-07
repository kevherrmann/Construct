import { useTranslation } from 'react-i18next'
import type { ChatAuftrag } from '@/api/team'
import { useSettings } from '@/stores/settings'
import s from './Firma.module.css'

/** Umschalter über der Eingabe, solange die Firma in diesem Chat arbeitet. */
export function EinwurfWahl({
  auftrag,
  anFirma,
  setAnFirma,
}: {
  auftrag: ChatAuftrag
  anFirma: boolean
  setAnFirma: (v: boolean) => void
}) {
  const { t } = useTranslation()
  const assistent = useSettings((st) => st.boot.assistant)
  return (
    <div className={s.einwurfWahl}>
      <span className={s.leise}>🏢 {t('Die Firma arbeitet an „{t}“', { t: auftrag.titel })}</span>
      <span className={s.pillen}>
        {t('Nachricht an')}
        <button
          type="button"
          className={`${s.pille} ${!anFirma ? s.an : ''}`}
          onClick={() => setAnFirma(false)}
        >
          {assistent || t('Assistent')}
        </button>
        <button
          type="button"
          className={`${s.pille} ${anFirma ? s.an : ''}`}
          title={t('Landet im laufenden Zug, ohne zusätzlichen Schritt')}
          onClick={() => setAnFirma(true)}
        >
          {t('Firma')}
        </button>
      </span>
    </div>
  )
}
