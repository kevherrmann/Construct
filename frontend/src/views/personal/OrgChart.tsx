import { useTranslation } from 'react-i18next'
import { useBelegschaft, type OrgNode } from '@/api/team'
import { usePersonal } from './store'
import s from './Personal.module.css'

/** Organigramm: verschachtelte Kästen aus `reports_to`. Zyklen hat der Server
 *  schon gekappt — sie stehen hier als eigene Wurzel mit Warnung. */
function Karte({ n }: { n: OrgNode }) {
  const zeigeAkte = usePersonal((st) => st.zeigeAkte)
  return (
    <>
      <button
        type="button"
        className={s.orgkarte}
        style={{ ['--accent-rgb' as string]: n.color }}
        onClick={() => zeigeAkte(n.slug)}
      >
        <b>
          {n.name}
          {n.problems.length > 0 && <span className={s.warn}> ⚠</span>}
        </b>
        <span className={s.ot}>{n.title}</span>
        <span className={s.om}>
          {n.model} · {n.effort}
        </span>
      </button>
      {n.reports.length > 0 && (
        <div className={s.orgzeile}>
          {n.reports.map((k) => (
            <div key={k.slug} className={s.orgast}>
              <Karte n={k} />
            </div>
          ))}
        </div>
      )}
    </>
  )
}

export function OrgChart() {
  const { t } = useTranslation()
  const { data } = useBelegschaft()
  return (
    <div className={s.wrap}>
      <h2 className={s.h2}>⛭ {t('Organigramm')}</h2>
      <div className={s.orgwrap}>
        {data?.org.roots.map((r) => (
          <div key={r.slug} className={s.orgast}>
            <Karte n={r} />
          </div>
        ))}
        {data && !data.org.roots.length && <div className={s.hint}>{t('leer')}</div>}
      </div>
      {!!data?.org.cycles.length && (
        <div className={s.fehler}>
          ⚠ {t('Kreisbezug in')} <b>{data.org.cycles.join(', ')}</b>{' '}
          {t(
            '— diese Akten zeigen im Kreis aufeinander. Sie stehen jetzt als eigene Wurzel da; korrigiere „berichtet an“.',
          )}
        </div>
      )}
    </div>
  )
}
