import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useUserMd, useUserMdSpeichern } from '@/api/team'
import s from './Personal.module.css'

function Formular({ start, ergaenzt }: { start: string; ergaenzt: string }) {
  const { t } = useTranslation()
  const speichern = useUserMdSpeichern()
  const [text, setText] = useState(start)
  const [zusatz, setZusatz] = useState(ergaenzt)
  const [basis, setBasis] = useState({ text: start, zusatz: ergaenzt })
  const [msg, setMsg] = useState('')
  return (
    <div className={s.akte}>
      <div className={s.hinweis} style={{ marginLeft: 0 }}>
        {t(
          'Diese Datei hängt an jedem Systemprompt des Assistenten und der Mitarbeiter. Du darfst sie frei bearbeiten.',
        )}
      </div>
      <textarea
        className={s.text}
        style={{ minHeight: 260 }}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className={s.hinweis} style={{ marginLeft: 0, marginTop: 14 }}>
        <b>{t('Von Mitarbeitern ergänzt')}</b> —{' '}
        {t(
          'was sie über dich gelernt haben (user_merken). Das sehen nur die Mitarbeiter, nicht der Assistent im Chat; was du für richtig hältst, übernimmst du oben.',
        )}
      </div>
      <textarea
        className={s.text}
        style={{ minHeight: 120 }}
        value={zusatz}
        onChange={(e) => setZusatz(e.target.value)}
      />
      <div className={s.aktionen} style={{ marginLeft: 0 }}>
        <button
          type="button"
          className={s.knopf}
          disabled={speichern.isPending}
          onClick={() => {
            // Nur Geändertes senden: die Mitarbeiter schreiben in die Ergänzungen, während
            // dieses Fenster offen ist.
            const neu: { text?: string; ergaenzungen?: string } = {}
            if (text !== basis.text) neu.text = text
            if (zusatz !== basis.zusatz) neu.ergaenzungen = zusatz
            speichern.mutate(neu, {
              onSuccess: () => {
                setBasis({ text, zusatz })
                setMsg(`✓ ${t('gespeichert')}`)
              },
              onError: () => setMsg(t('Fehler beim Speichern')),
            })
          }}
        >
          {t('SPEICHERN')}
        </button>
        <span className={s.msg}>{msg}</span>
      </div>
    </div>
  )
}

/** Was die Firma über den Nutzer weiß: seine USER.md (dieselbe wie die des Assistenten)
 *  und, getrennt, was die Mitarbeiter ergänzt haben. */
export function UserMd() {
  const { t } = useTranslation()
  const { data } = useUserMd()
  return (
    <div className={s.wrap}>
      <h2 className={s.h2}>📓 {t('Was die Firma über dich weiß')}</h2>
      {/* Erst wenn der Text da ist: das Formular übernimmt ihn als Startwert. */}
      {data ? <Formular start={data.text} ergaenzt={data.ergaenzungen} /> : <div>⟲ …</div>}
    </div>
  )
}
