import { useTranslation } from 'react-i18next'
import { useBelegschaft } from '@/api/team'
import { Avatar } from './Person'
import { usePersonal } from './store'
import s from './Personal.module.css'

// Seitenleiste: die Belegschaft, darüber Organigramm und die gemeinsame USER.md.
export function PersonalSide() {
  const { t } = useTranslation()
  const { data, isPending } = useBelegschaft()
  const { ansicht, slug, zeigeOrg, zeigeAkte, zeigeUser } = usePersonal()
  return (
    <div>
      <button
        type="button"
        className={`${s.nav} ${ansicht === 'org' ? s.sel : ''}`}
        onClick={zeigeOrg}
      >
        ⛭ {t('Organigramm')}
      </button>
      <button
        type="button"
        className={`${s.nav} ${ansicht === 'user' ? s.sel : ''}`}
        onClick={zeigeUser}
      >
        📓 {t('Was die Firma über dich weiß')}
      </button>
      <div className={s.uh}>{t('BELEGSCHAFT')}</div>
      {!isPending && !data?.agents.length && (
        <div className={s.hint}>{t('Noch niemand eingestellt.')}</div>
      )}
      {data?.agents.map((a) => (
        <button
          key={a.slug}
          type="button"
          className={`${s.emp} ${ansicht === 'akte' && slug === a.slug ? s.sel : ''}`}
          style={{ ['--accent-rgb' as string]: a.color }}
          onClick={() => zeigeAkte(a.slug)}
        >
          <Avatar p={a} groesse={30} />
          <span className={s.en}>
            <b>
              {a.name}
              {a.problems.length > 0 && (
                <span className={s.warn} title={t('Akte fehlerhaft')}>
                  {' '}
                  ⚠
                </span>
              )}
              {a.status === 'paused' && <span className={s.pause}> ⏸</span>}
            </b>
            <i>{a.title}</i>
          </span>
        </button>
      ))}
    </div>
  )
}
