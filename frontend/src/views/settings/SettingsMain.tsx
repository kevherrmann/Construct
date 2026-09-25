import { useEffect, useState, type ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettings } from '@/stores/settings'
import { BackgroundSection, ThemeSection } from './AppearanceSections'
import { EnginesSection } from './EnginesSection'
import { LanguageSection, MailSection, TilesSection } from './GeneralSections'
import { NamesSection } from './NamesSection'
import { Note } from './parts'
import { PersonaSection } from './PersonaSection'
import { TelegramSection } from './TelegramSection'
import { TtsSection } from './TtsSection'
import { UpdatesSection } from './UpdatesSection'
import { SECTIONS, type SectionId } from './sections'
import s from './Settings.module.css'

// „✓ gespeichert“ unten rechts nach jedem Speichern über den Store; nur auf
// Änderungen hören, damit ein alter Stand beim Öffnen nicht aufblitzt.
function SavedNote() {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    const unsub = useSettings.subscribe((st, prev) => {
      if (st.saveState === prev.saveState) return
      clearTimeout(timer)
      if (st.saveState === 'saved') {
        setText(t('✓ gespeichert'))
        timer = setTimeout(() => setText(''), 1600)
      } else if (st.saveState === 'error') setText(t('⚠ nicht gespeichert'))
    })
    return () => {
      unsub()
      clearTimeout(timer)
    }
  }, [t])
  return (
    <div style={{ textAlign: 'right' }}>
      <Note text={text} />
    </div>
  )
}

const BY_ID: Record<SectionId, ComponentType> = {
  sprache: LanguageSection,
  kacheln: TilesSection,
  modelle: EnginesSection,
  mail: MailSection,
  vorlesen: TtsSection,
  telegram: TelegramSection,
  updates: UpdatesSection,
  namen: NamesSection,
  charakter: PersonaSection,
  farbwelt: ThemeSection,
  hintergrund: BackgroundSection,
}

// Serverseitig gespeichert (settings.json), nicht im localStorage: die App
// wird mal aus dem Fenster, mal aus dem Browser bedient, und zwei Browser
// wären sonst zwei verschiedene Wahrheiten.
export function SettingsMain() {
  return (
    <div className={s.page}>
      <div className={s.wrap}>
        {SECTIONS.map(({ id }) => {
          const Sec = BY_ID[id]
          return <Sec key={id} />
        })}
        <SavedNote />
      </div>
    </div>
  )
}
