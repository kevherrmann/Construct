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

/** Ordnerbaum unter dem Workspace. Projekte (.git, CLAUDE.md, package.json …)
 *  haben keine Kinder — aufklappbar sind nur Sammelordner wie "kunden". */
export interface FolderNode {
  path: string
  name: string
  project: boolean
  children: FolderNode[]
}

export const useFolderTree = () =>
  useQuery({
    queryKey: ['folders', 'tree'],
    queryFn: () => apiGet<FolderNode>('/api/folders/tree'),
  })

export interface Werkstatt {
  cwd: string
  dateien: { path: string; neu: boolean; mal: number; ts: string }[]
  befehle: {
    command: string
    description: string
    output: string | null
    isError: boolean
    ts: string
  }[]
  git: { repo: boolean; root: string; dateien: { path: string; status: string }[] }
}

/** Werkbank und Fernseher im Construct-Raum: Dateien und Befehle der ganzen
 *  Session, aus dem Protokoll (der geladene Verlauf kennt nur Text). Läuft
 *  gerade etwas, alle paar Sekunden neu — claude schreibt das Protokoll mit. */
export const useWerkstatt = (sid: string | null | undefined, busy: boolean, stand: number) =>
  useQuery({
    queryKey: ['werkstatt', sid, stand],
    queryFn: () => apiGet<Werkstatt>(`/api/werkstatt/${encodeURIComponent(sid!)}`),
    enabled: !!sid && !sid.startsWith('llm-') && !sid.startsWith('hermes-'),
    refetchInterval: busy ? 4000 : false,
    placeholderData: (alt) => alt,
    retry: false,
  })
