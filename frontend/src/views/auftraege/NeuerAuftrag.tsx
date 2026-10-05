import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuftragNeu } from '@/api/team'
import { useAuftraegeAnsicht } from './store'
import s from './Auftraege.module.css'

export function NeuerAuftrag() {
  const { t } = useTranslation()
  const oeffne = useAuftraegeAnsicht((st) => st.oeffne)
  const neu = useAuftragNeu()
  const [brief, setBrief] = useState('')
  const [titel, setTitel] = useState('')
  const [fehler, setFehler] = useState('')
  const los = () => {
    if (!brief.trim()) return setFehler(t('… und worum geht es?'))
    setFehler('')
    neu.mutate(
      { brief: brief.trim(), titel: titel.trim() },
      { onSuccess: (j) => oeffne(j.ticket.id), onError: (e) => setFehler(e.message) },
    )
  }
  return (
    <div className={s.wrap}>
      <h2 className={s.h2}>＋ {t('Neuer Auftrag')}</h2>
      <div className={s.karte}>
        <div className={s.hinweis}>
          {t(
            'Der Auftrag geht an die Geschäftsführung. Sie verteilt ihn und meldet sich, wenn etwas unklar ist oder sich die Firma im Kreis dreht.',
          )}
        </div>
        <label className={s.lbl}>{t('WORUM GEHT ES?')}</label>
        <textarea
          className={s.text}
          style={{ minHeight: 130 }}
          autoFocus
          value={brief}
          placeholder={t('Beschreib die Aufgabe so, wie du sie einem Menschen geben würdest.')}
          onChange={(e) => setBrief(e.target.value)}
        />
        <label className={s.lbl}>
          {t('TITEL')} <span className={s.leise}>({t('optional')})</span>
        </label>
        <input
          className={s.feld}
          maxLength={120}
          value={titel}
          placeholder={t('wird sonst aus dem Text genommen')}
          onChange={(e) => setTitel(e.target.value)}
        />
        <div className={s.aktionen}>
          <button type="button" className={s.knopf} disabled={neu.isPending} onClick={los}>
            {t('AUFTRAG ERTEILEN')}
          </button>
          <span className={s.msg}>{fehler}</span>
        </div>
      </div>
    </div>
  )
}
