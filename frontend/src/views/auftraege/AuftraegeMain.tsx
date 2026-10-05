import { useTranslation } from 'react-i18next'
import { AuftragAnsicht } from './AuftragAnsicht'
import { NeuerAuftrag } from './NeuerAuftrag'
import { useAuftraegeAnsicht } from './store'
import s from './Auftraege.module.css'

export function AuftraegeMain() {
  const { t } = useTranslation()
  const auswahl = useAuftraegeAnsicht((st) => st.auswahl)
  if (auswahl === 'neu') return <NeuerAuftrag />
  if (auswahl) return <AuftragAnsicht key={auswahl} id={auswahl} />
  return (
    <div className={s.wrap}>
      <div className={s.leer}>{t('Links einen Auftrag wählen — oder einen neuen erteilen.')}</div>
    </div>
  )
}
