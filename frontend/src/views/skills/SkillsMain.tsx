import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router'
import { useSkillFile, useSkills, type Skill } from '@/api/skills'
import { MarkdownBubble } from '@/components/chat/MarkdownBubble'
import s from './SkillsMain.module.css'

// Angeklickter Skill im Hauptbereich. Der Pfad steht in der URL (?path=…), so
// überlebt die Ansicht ein Neuladen; Name und Art kommen aus der Liste.
export function SkillsMain() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const path = params.get('path')
  const skills = useSkills().data
  const file = useSkillFile(path)
  if (!path) return null

  const sk: Skill | undefined = Object.values(skills ?? {})
    .flat()
    .find((x) => x.path === path)
  const kind = sk?.kind ?? (path.endsWith('.py') ? 'py' : 'md')
  // Ohne Liste (direkt per URL): wie das Backend benennen — Ordner der SKILL.md
  // bzw. Dateiname ohne .py.
  const parts = path.split('/')
  const name =
    sk?.name ??
    (kind === 'py' ? parts[parts.length - 1]!.slice(0, -3) : parts[parts.length - 2]) ??
    path

  if (file.isPending) return <div className={`${s.page} ${s.tool}`}>⟲ …</div>
  const content = file.data?.content || t('(leer / nicht lesbar)')

  return (
    <div className={s.page}>
      <div className={s.head}>
        <span>📄 {name}</span>
        {/* Früher: zurück in eine neue Chat-Session. */}
        <button className={s.back} onClick={() => navigate('/chat')}>
          {t('← zurück')}
        </button>
      </div>
      <MarkdownBubble
        key={path}
        text={kind === 'py' ? '```python\n' + content + '\n```' : content}
      />
    </div>
  )
}
