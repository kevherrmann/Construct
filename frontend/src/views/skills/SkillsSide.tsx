import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useSkills } from '@/api/skills'
import { useSkillsUi } from './store'
import s from './SkillsSide.module.css'

// Skills aus allen Projekten, gruppiert nach Projekt; ein Klick zeigt die Datei rechts.
export function SkillsSide() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data, isPending } = useSkills()
  const closed = useSkillsUi((st) => st.closed)
  const toggle = useSkillsUi((st) => st.toggle)
  const projs = Object.keys(data ?? {})

  let body
  if (isPending) body = <div className={s.hint}>{t('⟲ lade…')}</div>
  else if (!projs.length) body = <div className={s.hint}>{t('keine Skills gefunden')}</div>
  else
    body = projs.map((proj) => {
      const open = !closed[proj]
      const items = data![proj]!
      return (
        <div key={proj}>
          <div className={s.folder} onClick={() => toggle(proj)}>
            <span className={s.fa}>{open ? '▾' : '▸'}</span>
            <span className={s.fn}>▣ {proj}</span>
            <span className={s.fc}>{items.length}</span>
          </div>
          {open &&
            items.map((sk) => (
              <div
                key={sk.path}
                className={s.sess}
                onClick={() => navigate(`/skills?path=${encodeURIComponent(sk.path)}`)}
              >
                <span className={s.t}>⚡ {sk.name}</span>
                <span className={s.d}>{sk.desc}</span>
              </div>
            ))}
        </div>
      )
    })

  return (
    <div>
      <div className={s.hint}>{t('Skills aus deinen Projekten — anklicken zum Ansehen')}</div>
      {body}
    </div>
  )
}
