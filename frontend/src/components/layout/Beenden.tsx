import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { beenden, istLokal } from '@/api/system'
import { Dialog } from '@/components/dialogs/Dialog'
import s from './Beenden.module.css'

// ⏻ CONSTRUCT beenden. Seit das Fenster ein Browser-Fenster ist, läuft der
// Server nach dem Schließen weiter (Telegram, geplante Aufgaben) — beenden
// geht darum hier. Fragt einmal nach, danach steht nur noch ein Hinweis da.

export function BeendenKnopf({
  className,
  mitText = false,
}: {
  className?: string
  mitText?: boolean
}) {
  const { t } = useTranslation()
  const [frage, setFrage] = useState(false)
  const [stand, setStand] = useState<'' | 'laeuft' | 'fertig' | 'fehler'>('')
  if (!istLokal()) return null

  const los = async () => {
    setStand('laeuft')
    try {
      await beenden()
      setStand('fertig')
      setFrage(false)
      // Das App-Fenster darf sich selbst schließen; ein normaler Tab meist nicht.
      setTimeout(() => window.close(), 1500)
    } catch {
      setStand('fehler')
    }
  }

  return (
    <>
      <button
        type="button"
        className={className}
        title={t('CONSTRUCT beenden')}
        aria-label={t('CONSTRUCT beenden')}
        onClick={() => setFrage(true)}
      >
        ⏻{mitText && ` ${t('CONSTRUCT beenden')}`}
      </button>
      <Dialog open={frage} onClose={() => setFrage(false)} title={t('CONSTRUCT beenden?')}>
        <p>
          {t(
            'Der Server fährt herunter. Telegram-Bot und geplante Aufgaben laufen danach nicht mehr, bis du CONSTRUCT wieder startest.',
          )}
        </p>
        {stand === 'fehler' && <p className={s.fehler}>⚠ {t('Beenden hat nicht geklappt.')}</p>}
        <div className={s.knoepfe}>
          <button type="button" className={s.nein} onClick={() => setFrage(false)}>
            {t('Abbrechen')}
          </button>
          <button
            type="button"
            className={s.ja}
            disabled={stand === 'laeuft'}
            onClick={() => void los()}
          >
            ⏻ {t('Beenden')}
          </button>
        </div>
      </Dialog>
      {stand === 'fertig' &&
        createPortal(
          <div className={s.ende}>
            <b>⏻</b>
            <p>{t('CONSTRUCT ist beendet.')}</p>
            <span>{t('Du kannst das Fenster schließen.')}</span>
          </div>,
          document.body,
        )}
    </>
  )
}
