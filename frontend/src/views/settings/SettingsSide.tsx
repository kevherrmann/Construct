import { useTranslation } from 'react-i18next'
import { SECTIONS, TABS, navLabel } from './sections'
import { useSettingsTab } from './tab'
import s from './SettingsSide.module.css'

// Navigation links: ein Tab je Bereich, rechts steht nur dieser Bereich.
export function SettingsSide() {
  const { t } = useTranslation()
  const [tab, setTab] = useSettingsTab()
  const titel = (id: string) => t(navLabel(SECTIONS.find((x) => x.id === id)!.title))
  return (
    <>
      <div className={s.vhint}>{t('Was du siehst und womit du redest — rechts einstellen')}</div>
      <nav>
        {TABS.map((x) => (
          <button
            key={x.id}
            type="button"
            className={`${s.item} ${tab === x.id ? s.active : ''}`}
            onClick={() => setTab(x.id)}
          >
            <span className={s.tabName}>{t(x.title)}</span>
            <span className={s.tabInhalt}>{x.sections.map(titel).join(' · ')}</span>
          </button>
        ))}
      </nav>
    </>
  )
}
