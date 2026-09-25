import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/lib/api'

export interface SessionInfo {
  id: string
  /** Ordner in ~/.claude/projects, "llm" oder "hermes" für fremde Anbieter. */
  project: string
  cwd: string
  title: string
  renamed: boolean
  mtime: number
  archived: boolean
  /** Sitzung eines FACTORIA-Agenten ("" = eigene). */
  agent: string
  provider?: string
  model?: string
}

export interface RunInfo {
  run_id: string
  session_id: string | null
}

export interface SessionDetail {
  id: string
  project: string
  offset: number
  model: string
  messages: { role: 'user' | 'assistant'; text: string }[]
}

export const useSessions = () =>
  useQuery({
    queryKey: ['sessions'],
    queryFn: async () => {
      const [sessions, runs] = await Promise.all([
        apiGet<SessionInfo[]>('/api/sessions'),
        apiGet<RunInfo[]>('/api/runs').catch(() => [] as RunInfo[]),
      ])
      const running: Record<string, string> = {}
      for (const r of runs) if (r.session_id) running[r.session_id] = r.run_id
      return { sessions, running }
    },
  })

export const useFolders = () =>
  useQuery({ queryKey: ['folders'], queryFn: () => apiGet<string[]>('/api/folders') })
