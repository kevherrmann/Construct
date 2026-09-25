import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SECTIONS, navLabel, sectionDomId, type SectionId } from './sections'
import s from './SettingsSide.module.css'

// Navigation links: springt zum Abschnitt rechts.
export function SettingsSide() {
  const { t } = useTranslation()
  const [active, setActive] = useState<SectionId | null>(null)
  const go = (id: SectionId) => {
    setActive(id)
    document
      .getElementById(sectionDomId(id))
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    <>
      <div className={s.vhint}>{t('Was du siehst und womit du redest — rechts einstellen')}</div>
      <nav>
        {SECTIONS.map((sec) => (
          <button
            key={sec.id}
            type="button"
            className={`${s.item} ${active === sec.id ? s.active : ''}`}
            onClick={() => go(sec.id)}
          >
            {t(navLabel(sec.title))}
          </button>
        ))}
      </nav>
    </>
  )
}
