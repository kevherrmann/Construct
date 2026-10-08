import { useTranslation } from 'react-i18next'
import { useUebergabeNachholen, type Uebergabe } from '@/api/team'
import s from './Firma.module.css'

/** Eine Übergabe an die Firma, die nicht ankam, weil der Team-Modus aus war. Steht
 *  unter der Antwort, die sie ausgelöst hat; der Knopf schaltet die Firma ein und
 *  holt die Übergabe nach. Danach bleibt eine leise Zeile stehen. */
export function UebergabeHinweis({ sid, u }: { sid: string; u: Uebergabe }) {
  const { t } = useTranslation()
  const nachholen = useUebergabeNachholen(sid)
  if (u.status === 'uebergeben')
    return (
      <div className={s.uebergeben}>
        ✓ {t('an die Firma übergeben')}: {u.titel}
      </div>
    )
  return (
    <section className={s.ausHinweis} aria-label={t('Auftrag nicht angekommen')}>
      <div className={s.ausKopf}>
        <span aria-hidden="true">⚠</span> {t('Die Firma ist aus, der Auftrag ist nicht angekommen')}
      </div>
      <div className={s.ausTitel}>{u.titel}</div>
      <div className={s.btns}>
        <button
          type="button"
          className={s.knopf}
          disabled={nachholen.isPending}
          onClick={() => nachholen.mutate(u.id)}
        >
          {nachholen.isPending ? t('übergebe …') : t('Firma einschalten und übergeben')}
        </button>
        {nachholen.error && (
          <span className={s.ausFehler} role="alert">
            ⚠ {nachholen.error.message}
          </span>
        )}
      </div>
    </section>
  )
}
