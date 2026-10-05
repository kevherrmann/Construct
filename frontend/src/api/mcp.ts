import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPost } from '@/lib/api'

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

export type McpTransport = 'stdio' | 'http' | 'sse'
export type McpScope = 'user' | 'local'

/** Eingabe für POST /api/mcp (server/routes/files.py, mcp_add). */
export interface McpNeu {
  name: string
  transport: McpTransport
  scope: McpScope
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string>
}

/** Was der Server zum Entfernen annimmt. Konnektoren von claude.ai
 *  ("claude.ai Gmail") und Plugin-Server lassen sich so nicht entfernen. */
export const MCP_NAME = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/

export const useMcp = () =>
  useQuery({
    queryKey: ['mcp'],
    queryFn: () => apiGet<McpList>('/api/mcp'),
    // `claude mcp list` prüft live (bis zu 30 s) — bei jedem Öffnen neu fragen.
    refetchOnMount: 'always',
  })

// Beide laufen über die CLI und brauchen Sekunden. Danach die Liste neu holen;
// den Fehler zeigt die Oberfläche selbst am Formular bzw. am Eintrag. Entfernen
// hat einen eigenen Hook je Eintrag, damit jeder seinen eigenen Zustand trägt.
export function useMcpHinzufuegen() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: McpNeu) => apiPost<{ ok: boolean }>('/api/mcp', v),
    // Die Eingabe enthält Geheimnisse (env, Header): nicht im Cache halten.
    gcTime: 0,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mcp'] }),
  })
}

export function useMcpEntfernen(name: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiDelete<{ ok: boolean }>(`/api/mcp/${encodeURIComponent(name)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mcp'] }),
  })
}
