import { useQuery, type QueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '@/lib/api'

// Externe KI-Anbieter (llm.public_providers) — ohne Keys, nur key_set.
export interface Provider {
  id: string
  label: string
  hint: string
  needs_key: boolean
  key_set: boolean
  base_url: string
  default_base: string
  configured: boolean
  models: string[]
  /** true = sicher werkzeugfähig, null = unbekannt. */
  tools: Record<string, boolean | null>
  /** Wie viele Modelle ohne Werkzeug-Aufrufe ausgeblendet wurden. */
  hidden: number
  error: string
}

export const PROV_ICON: Record<string, string> = {
  openai: '🟢',
  gemini: '✦',
  deepseek: '🐋',
  ollama: '🦙',
  bonsai: '🌱',
}

const fetchProviders = async (refresh = false) => {
  const list = await apiGet<Provider[]>('/api/llm/providers' + (refresh ? '?refresh=1' : ''))
  return Array.isArray(list) ? list : []
}

export const useProviders = () =>
  useQuery({ queryKey: ['llm-providers'], queryFn: () => fetchProviders() })

/**
 * Modell-Listen am Server frisch abfragen (statt aus dessen Cache) und allen
 * Nutzern der Liste — Dialog wie 🧠-Picker — unterschieben.
 */
export async function refreshProviders(qc: QueryClient) {
  try {
    qc.setQueryData(['llm-providers'], await fetchProviders(true))
  } catch {
    await qc.invalidateQueries({ queryKey: ['llm-providers'] })
  }
}

export interface ProviderSave {
  id: string
  enabled: boolean
  api_key?: string
  base_url?: string
}

export const saveProvider = (body: ProviderSave) =>
  apiPost<{ ok: boolean; models: number; error: string }>('/api/llm/providers', body)

// ---------- Bonsai (bonsai.status) ----------
export interface BonsaiStatus {
  available: boolean
  running: boolean
  model: string
  vram: boolean
  idle_min: number
}

export const useBonsai = () =>
  useQuery({ queryKey: ['bonsai'], queryFn: () => apiGet<BonsaiStatus>('/api/bonsai/status') })
export const stopBonsai = () => apiPost<BonsaiStatus>('/api/bonsai/stop')

// ---------- Ollama (app.ollama_models) ----------
export interface Progress {
  status: string
  total: number
  completed: number
  done: boolean
  error: string
}

export interface OllamaModels {
  installed: { name: string; size: number; param: string; quant: string }[]
  catalog: { name: string; size: string; desc: string }[]
  pulls: Record<string, Progress>
  error: string
  /** Programm vorhanden? */
  bin: boolean
  /** Eigene Installation (~/.cody-ollama); null = keine frische Meldung. */
  install: Progress | null
  reachable: boolean
}

/** Läuft gerade etwas, das man beobachten muss (Download, Installation)? */
export const ollamaBusy = (d?: OllamaModels) =>
  !!d &&
  ((!d.reachable && !!d.install && !d.install.done) ||
    Object.values(d.pulls ?? {}).some((p) => !p.done))

export const useOllama = (enabled: boolean) =>
  useQuery({
    queryKey: ['ollama'],
    queryFn: () => apiGet<OllamaModels>('/api/ollama/models'),
    enabled,
    // Downloads laufen server-seitig; solange einer läuft, Fortschritt pollen.
    refetchInterval: (q) => (ollamaBusy(q.state.data) ? 1200 : false),
  })

export const ollamaInstall = () => apiPost<unknown>('/api/ollama/install')
export const ollamaPull = (model: string) => apiPost<unknown>('/api/ollama/pull', { model })
export const ollamaCancel = (model: string) =>
  apiPost<{ cancelled: boolean }>('/api/ollama/pull_cancel', { model })
export const ollamaDelete = (model: string) =>
  apiPost<{ deleted: boolean }>('/api/ollama/delete', { model })
