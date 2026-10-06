import { useTranslation } from 'react-i18next'
import { useUi } from '@/stores/ui'
import { SECTIONS, TABS, navLabel } from './sections'
import { useSettingsTab } from './tab'
import s from './SettingsSide.module.css'

// Navigation links: ein Tab je Bereich, rechts steht nur dieser Bereich.
export function SettingsSide({ ohneHinweis = false }: { ohneHinweis?: boolean }) {
  const { t } = useTranslation()
  const [tab, setTab] = useSettingsTab()
  // Schmal liegt die Leiste als Schublade über dem Inhalt: nach der Wahl zu.
  const zu = useUi((st) => st.setSideOpen)
  const titel = (id: string) => t(navLabel(SECTIONS.find((x) => x.id === id)!.title))
  return (
    <>
      {/* Im Raum steht derselbe Satz schon als Untertitel der Projektion. */}
      {!ohneHinweis && (
        <div className={s.vhint}>{t('Was du siehst und womit du redest — rechts einstellen')}</div>
      )}
      <nav>
        {TABS.map((x) => (
          <button
            key={x.id}
            type="button"
            className={`${s.item} ${tab === x.id ? s.active : ''}`}
            onClick={() => (setTab(x.id), zu(false))}
          >
            <span className={s.tabName}>{t(x.title)}</span>
            <span className={s.tabInhalt}>{x.sections.map(titel).join(' · ')}</span>
          </button>
        ))}
      </nav>
    </>
  )
}
