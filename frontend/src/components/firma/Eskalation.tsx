import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuftragActions, type Auftrag, type Person } from '@/api/team'
import { Markdown } from '@/components/chat/Markdown'
import { BREMSEN } from '@/lib/team'
import { Avatar } from '@/views/personal/Person'
import s from './Firma.module.css'

/** Der Auftrag wartet auf den Nutzer. Die Frage steht da wie jede andere Nachricht
 *  im Verlauf (Bild, Name, Blase), nur mit einem Antwortfeld darunter: wer fragt,
 *  was passiert ist, was er wissen will. Die Antwort geht an genau den. */
export function Eskalation({
  auftrag,
  leute,
}: {
  auftrag: Pick<Auftrag, 'id' | 'status' | 'owner' | 'eskalation'>
  leute: Record<string, Person>
}) {
  const { t } = useTranslation()
  const act = useAuftragActions(auftrag.id)
  const [text, setText] = useState('')
  const [fehler, setFehler] = useState('')
  const e = auftrag.eskalation
  if (!e)
    return auftrag.status === 'fertig' ? (
      <div className={`${s.notiz} ${s.fertigbox}`}>✓ {t('Auftrag abgeschlossen')}</div>
    ) : null
  const p: Person = leute[e.an || auftrag.owner] ?? {
    name: t('die Geschäftsführung'),
    title: '',
    color: '126,231,135',
    avatar: '',
  }
  // Eine echte Rückfrage hat jemand gestellt; die anderen Bremsen hat die Firma
  // selbst gezogen (Schleife, zu viele Schritte …), dann steht ihr Name oben.
  const rueckfrage = e.bremse === 'eskaliert'
  const senden = (aktion: 'weiter' | 'abbrechen') => {
    setFehler('')
    act.antwort.mutate(
      { aktion, text },
      { onSuccess: () => setText(''), onError: (x) => setFehler(x.message) },
    )
  }
  return (
    <section className={s.eskal} style={{ ['--accent-rgb' as string]: p.color }}>
      <div className={s.eskalKopf}>
        ⏸ {rueckfrage ? t('Rückfrage') : t(BREMSEN[e.bremse] ?? e.bremse)} ·{' '}
        {t('der Auftrag wartet auf dich')}
      </div>
      <div className={s.zeile}>
        <Avatar p={p} groesse={32} />
        <div className={s.col}>
          <div className={s.who}>
            {p.name.toUpperCase()} · {t('fragt dich')}
          </div>
          <div className={s.bubble}>
            {e.grund && (
              <div className={s.anlass}>
                <Markdown text={e.grund} />
              </div>
            )}
            <Markdown text={e.frage} />
          </div>
        </div>
      </div>
      <div className={s.antwort}>
        <textarea
          className={s.text}
          value={text}
          rows={2}
          placeholder={t('Deine Antwort an {n} …', { n: p.name })}
          onChange={(x) => setText(x.target.value)}
          onKeyDown={(x) => {
            if (x.key === 'Enter' && (x.ctrlKey || x.metaKey) && !act.antwort.isPending) {
              x.preventDefault()
              senden('weiter')
            }
          }}
        />
        <div className={s.btns}>
          <button
            type="button"
            className={s.knopf}
            disabled={act.antwort.isPending}
            onClick={() => senden('weiter')}
          >
            {text.trim() ? t('ANTWORTEN') : t('WEITERMACHEN')}
          </button>
          <span className={s.leise}>
            {text.trim()
              ? t('Strg+Enter schickt ab')
              : t('Ohne Text heißt das: „Mach bitte weiter.“')}
          </span>
          <button
            type="button"
            className={`${s.knopf} ${s.gefahr}`}
            disabled={act.antwort.isPending}
            onClick={() => senden('abbrechen')}
          >
            {t('abbrechen')}
          </button>
          <span className={s.msg}>{fehler && `⚠ ${fehler}`}</span>
        </div>
      </div>
    </section>
  )
}
