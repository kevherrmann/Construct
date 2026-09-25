import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/lib/api'

export interface Skill {
  name: string
  desc: string
  /** Absoluter Pfad zur SKILL.md bzw. .py — Schlüssel für /api/skill. */
  path: string
  kind: 'md' | 'py'
}

/** Projekt (bzw. "★ global (alle Projekte)") → Skills. */
export type SkillGroups = Record<string, Skill[]>

export interface SkillFile {
  path: string
  content: string
}

export const useSkills = () =>
  useQuery({
    queryKey: ['skills'],
    queryFn: () => apiGet<SkillGroups>('/api/skills'),
    // Beim Öffnen der Ansicht neu einlesen — Skills entstehen nebenbei im Chat.
    refetchOnMount: 'always',
  })

export const useSkillFile = (path: string | null) =>
  useQuery({
    queryKey: ['skill', path],
    queryFn: () => apiGet<SkillFile>(`/api/skill?path=${encodeURIComponent(path!)}`),
    enabled: !!path,
    refetchOnMount: 'always',
  })
