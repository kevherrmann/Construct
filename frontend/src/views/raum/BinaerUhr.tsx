import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { bcdSpalten, ZEILEN } from './binaer'
import s from './Raum.module.css'

// Binäruhr in BCD: jede Ziffer von HH:MM:SS eine Spalte, unten 1, darüber
// 2, 4, 8. Punkte, die eine Ziffer nie braucht (die Zehner der Stunde gehen
// nur bis 2), gibt es gar nicht — so sieht man die Form der Uhr.

export function BinaerUhr({ jetzt }: { jetzt: Date }) {
  const { t } = useTranslation()
  const spalten = bcdSpalten(jetzt)
  const zeit = jetzt.toTimeString().slice(0, 8)
  return (
    <div className={s.binaer} role="img" aria-label={t('Binäruhr: {zeit}', { zeit })}>
      <div className={s.binaerWerte} aria-hidden="true">
        {ZEILEN.map((z) => (
          <span key={z}>{z}</span>
        ))}
      </div>
      {spalten.map((sp, i) => (
        <Fragment key={i}>
          {i > 0 && i % 2 === 0 && (
            <div
              className={`${s.binaerTrenner} ${jetzt.getSeconds() % 2 ? s.binaerAus : ''}`}
              aria-hidden="true"
            >
              <span />
              <span />
            </div>
          )}
          <div className={s.binaerSpalte} aria-hidden="true">
            {ZEILEN.map((z) =>
              z >= 2 ** sp.bits ? (
                <i key={z} className={s.binaerLeer} />
              ) : (
                <i key={z} className={sp.wert & z ? s.binaerAn : ''} />
              ),
            )}
            <b>{sp.wert}</b>
          </div>
        </Fragment>
      ))}
    </div>
  )
}
