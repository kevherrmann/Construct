import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/lib/api'

/** Ein Eintrag aus `claude mcp list`. */
export interface McpServer {
  name: string
  url: string
  /** Rohtext der CLI, z. B. "✔ Connected" oder "! Needs authentication". */
  status: string
  ok: boolean
  needs_auth: boolean
}

export interface McpList {
  servers: McpServer[]
  /** Nur gesetzt, wenn die CLI gar nicht lief. */
  error?: string
}

export const useMcp = () =>
  useQuery({
    queryKey: ['mcp'],
    queryFn: () => apiGet<McpList>('/api/mcp'),
    // `claude mcp list` prüft live (bis zu 30 s) — bei jedem Öffnen neu fragen.
    refetchOnMount: 'always',
  })
