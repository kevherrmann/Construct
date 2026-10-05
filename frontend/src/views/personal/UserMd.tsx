import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useUserMd, useUserMdSpeichern } from '@/api/team'
import s from './Personal.module.css'

function Formular({ start }: { start: string }) {
  const { t } = useTranslation()
  const speichern = useUserMdSpeichern()
  const [text, setText] = useState(start)
  const [msg, setMsg] = useState('')
  return (
    <div className={s.akte}>
      <div className={s.hinweis}>
        {t(
          'Diese Datei hängt an jedem Systemprompt und gehört dem Assistenten und allen Mitarbeitern. Sie ergänzen hier nur (nie überschreiben) — jede Zeile trägt, von wem sie stammt. Du darfst frei bearbeiten.',
        )}
      </div>
      <textarea
        className={s.text}
        style={{ minHeight: 340 }}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className={s.aktionen}>
        <button
          type="button"
          className={s.knopf}
          disabled={speichern.isPending}
          onClick={() =>
            speichern.mutate(text, {
              onSuccess: () => setMsg(`✓ ${t('gespeichert')}`),
              onError: () => setMsg(t('Fehler beim Speichern')),
            })
          }
        >
          {t('SPEICHERN')}
        </button>
        <span className={s.msg}>{msg}</span>
      </div>
    </div>
  )
}

/** Die gemeinsame USER.md. Frei bearbeiten darf sie nur der Nutzer — die
 *  Mitarbeiter hängen über `user_merken` an, sie ersetzen nie. */
export function UserMd() {
  const { t } = useTranslation()
  const { data } = useUserMd()
  return (
    <div className={s.wrap}>
      <h2 className={s.h2}>📓 {t('Was die Firma über dich weiß')}</h2>
      {/* Erst wenn der Text da ist: das Formular übernimmt ihn als Startwert und
          lässt sich danach nicht mehr von Nachladen überschreiben. */}
      {data ? <Formular start={data.text} /> : <div>⟲ …</div>}
    </div>
  )
}
