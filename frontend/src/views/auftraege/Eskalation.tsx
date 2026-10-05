import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuftragActions, type Auftrag, type Person } from '@/api/team'
import { BREMSEN } from '@/lib/team'
import s from './Auftraege.module.css'

/** Der Auftrag wartet auf den Nutzer: drei Zeilen, die er nicht suchen muss — was
 *  passiert ist, was er tun kann, an wen sein Wort geht. */
export function Eskalation({
  auftrag,
  leute,
}: {
  auftrag: Auftrag
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
  const wer = (e.an && leute[e.an]?.name) || leute[auftrag.owner]?.name || t('die Geschäftsführung')
  const senden = (aktion: 'weiter' | 'abbrechen') => {
    setFehler('')
    act.antwort.mutate(
      { aktion, text },
      { onSuccess: () => setText(''), onError: (x) => setFehler(x.message) },
    )
  }
  return (
    <div className={s.eskal}>
      <h4>
        ⏸ {t(BREMSEN[e.bremse] ?? e.bremse)} — {t('der Auftrag wartet auf dich')}
      </h4>
      <div>
        <span className={s.lbl}>{t('Was passiert ist:')}</span> {e.grund}
      </div>
      <div className={s.frage}>
        <span className={s.lbl}>{t('Was du tun kannst:')}</span> {e.frage}
      </div>
      <div className={s.anwen}>
        {t('Deine Antwort geht an')} <b>{wer}</b>. {t('Leer + WEITERMACHEN = „Mach bitte weiter.“')}
      </div>
      <textarea
        className={s.text}
        value={text}
        placeholder={t('Optional: Anweisung an {n} …', { n: wer })}
        onChange={(x) => setText(x.target.value)}
      />
      <div className={s.btns}>
        <button
          type="button"
          className={s.knopf}
          disabled={act.antwort.isPending}
          onClick={() => senden('weiter')}
        >
          {t('WEITERMACHEN')}
        </button>
        <span className={s.leise}>{t('setzt die Bremsen zurück')}</span>
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
  )
}
