import { useTranslation } from 'react-i18next'

// Übergangsweise für Bereiche, die noch nicht umgezogen sind.
export function Placeholder() {
  const { t } = useTranslation()
  return <div style={{ padding: 16, opacity: 0.6, fontSize: 12 }}>{t('Kommt gleich …')}</div>
}
