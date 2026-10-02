import { useTranslation } from 'react-i18next'
import { useProviders } from '@/api/providers'
import { useVersion } from '@/api/system'
import { modelInfo } from '@/lib/chat/models'
import { baseName } from '@/lib/format'
import { useChat } from '@/stores/chat'
import { useSettings } from '@/stores/settings'
import { openClaudeAuth } from '@/stores/dialogs'
import { Hud } from './Hud'
import s from './Topbar.module.css'

export function Topbar({ onBurger }: { onBurger: () => void }) {
  const { t } = useTranslation()
  const version = useVersion()
  const providers = useProviders()
  const workspace = useSettings((st) => st.boot.workspace)
  const conv = useChat((st) => st.active())
  // Womit zuletzt WIRKLICH geantwortet wurde — nicht die Auswahl, die kann
  // "Standard" sein oder ein Alias. Leer, solange in dieser Session nichts lief.
  const last = conv?.lastModel
  const lastLabel = last ? (modelInfo(last, providers.data)?.l ?? last.replace(/^claude-/, '')) : ''
  const cwd = conv?.cwd ?? workspace
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
        {lastLabel && (
          <span
            className={s.meta}
            title={t('Modell, mit dem in dieser Session zuletzt wirklich geantwortet wurde')}
          >
            · {t(lastLabel)}
          </span>
        )}
      </span>
      <Hud onAuthClick={openClaudeAuth} />
      <span className={s.sid} title={cwd || t('(unbekannt)')}>
        ▣ {baseName(cwd)}
      </span>
    </div>
  )
}
