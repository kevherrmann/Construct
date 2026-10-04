import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPost } from '@/lib/api'

export interface Version {
  version: string
  runtime: string
  workspace: string
  assistant: string
  claude: boolean
  code: string
}

export interface AuthStatus {
  cli: boolean
  can_web_login: boolean
  ok: boolean
  web_token: boolean
  env_token: boolean
}

export interface UsageWindow {
  percent: number | null
  resets_at: string | null
}

export interface Usage {
  available: boolean
  reason?: string
  five_hour?: UsageWindow
  seven_day?: UsageWindow
  /** Unix-Zeit, bis zu der das Limit greift; 0 = keins. */
  limit_hit: number
}

const FIVE_MIN = 5 * 60 * 1000

export const useVersion = () =>
  useQuery({
    queryKey: ['version'],
    queryFn: () => apiGet<Version>('/api/version'),
    staleTime: Infinity,
  })

export const useAuthStatus = () =>
  useQuery({
    queryKey: ['auth-status'],
    queryFn: () => apiGet<AuthStatus>('/api/auth/status'),
    refetchInterval: FIVE_MIN,
  })

export const useUsage = (enabled: boolean) =>
  useQuery({
    queryKey: ['usage'],
    queryFn: () => apiGet<Usage>('/api/usage'),
    refetchInterval: FIVE_MIN,
    enabled,
  })

/** CONSTRUCT beenden (⏻). Der Server nimmt das nur vom eigenen Rechner an. */
export const beenden = () => apiPost<{ ok: boolean }>('/api/shutdown')

/** Läuft die Oberfläche auf demselben Rechner wie der Server? Nur dann gibt es ⏻. */
export const istLokal = () => ['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname)
