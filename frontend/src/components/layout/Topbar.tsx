import { useTranslation } from 'react-i18next'
import { useVersion } from '@/api/system'
import { Hud } from './Hud'
import s from './Topbar.module.css'

export function Topbar({ onBurger }: { onBurger: () => void }) {
  const { t } = useTranslation()
  const version = useVersion()
  return (
    <div className={s.topbar}>
      <button type="button" className={s.burger} onClick={onBurger} aria-label="Menu">
        ☰
      </button>
      <span>
        <span className={s.dot}>●</span> {t('VERBUNDEN')}
        <span className={s.meta}>
          build {version.data?.version ?? (version.isError ? t('ALT/unbekannt') : '…')}
        </span>
      </span>
      <Hud />
    </div>
  )
}
