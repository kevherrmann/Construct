import { apiPost } from '@/lib/api'

// Web-Login: der Server steuert `claude auth login` über ein Pseudo-Terminal.
// Start liefert die OAuth-URL, danach wird der Code aus dem Browser eingereicht.
export const startLogin = () => apiPost<{ url: string }>('/api/auth/login')
export const submitLoginCode = (code: string) =>
  apiPost<{ ok: boolean }>('/api/auth/code', { code })
