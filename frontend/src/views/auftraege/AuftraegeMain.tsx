import { useTranslation } from 'react-i18next'
import { useMedien } from '@/hooks/useMedien'
import { AuftragAnsicht } from './AuftragAnsicht'
import { NeuerAuftrag } from './NeuerAuftrag'
import { useAuftraegeAnsicht } from './store'
import s from './Auftraege.module.css'

/** Schmal klappt die Seitenleiste mit der Liste weg (AppShell, gleiche Grenze). */
const SCHMAL = '(max-width: 900px)'

/** `gestapelt`: die Liste steht direkt darüber (Raum auf dem Handy) — dann braucht
 *  es keinen Hinweis, wo sie ist. */
export function AuftraegeMain({ gestapelt = false }: { gestapelt?: boolean }) {
  const { t } = useTranslation()
  const auswahl = useAuftraegeAnsicht((st) => st.auswahl)
  const schmal = useMedien(SCHMAL)
  if (auswahl === 'neu') return <NeuerAuftrag />
  if (auswahl) return <AuftragAnsicht key={auswahl} id={auswahl} />
  if (gestapelt) return null
  return (
    <div className={s.wrap}>
      <div className={s.leer}>
        {schmal
          ? t('Über ☰ einen Auftrag wählen — oder einen neuen erteilen.')
          : t('Links einen Auftrag wählen — oder einen neuen erteilen.')}
      </div>
    </div>
  )
}
