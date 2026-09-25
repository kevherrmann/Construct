import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { initI18n } from '@/lib/i18n'
import { openDialog, useDialogs } from '@/stores/dialogs'
import { ProvidersDialog } from './ProvidersDialog'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } })

const OLLAMA = {
  id: 'ollama',
  label: 'Ollama (lokal)',
  hint: '',
  needs_key: false,
  key_set: false,
  base_url: 'http://127.0.0.1:11434/v1',
  default_base: 'http://127.0.0.1:11434/v1',
  configured: true,
  models: ['gemma3:4b'],
  tools: {},
  hidden: 0,
  error: '',
}

const MODELS = {
  installed: [{ name: 'gemma3:4b', size: 3_300_000_000, param: '4B', quant: 'Q4_K_M' }],
  catalog: [
    { name: 'gemma3:4b', size: '3,3 GB', desc: '' },
    { name: 'mistral:7b', size: '4,1 GB', desc: '' },
  ],
  pulls: { 'qwen3.5:4b': { status: 'pulling', total: 200, completed: 50, done: false, error: '' } },
  error: '',
  bin: true,
  install: null,
  reachable: true,
}

beforeAll(() => {
  initI18n('de')
})
afterEach(() => {
  vi.restoreAllMocks()
  useDialogs.getState().close()
})

it('zeigt installierte Modelle, Downloads und Katalog; Löschen fragt nach', async () => {
  const fetch = vi.spyOn(window, 'fetch').mockImplementation(async (u) => {
    const url = String(u)
    if (url.startsWith('/api/llm/providers')) return json([OLLAMA])
    if (url === '/api/ollama/models') return json(MODELS)
    return json({})
  })
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ProvidersDialog />
    </QueryClientProvider>,
  )
  act(() => openDialog('providers'))

  expect(await screen.findByText('🦙 gemma3:4b')).toBeInTheDocument()
  expect(screen.getByText('3,3 GB · 4B · Q4_K_M')).toBeInTheDocument()
  expect(screen.getByText('25% · 0 MB / 0 MB')).toBeInTheDocument()
  // Schon installiert → nicht mehr im Angebot.
  expect(screen.getByText('mistral:7b')).toBeInTheDocument()
  expect(screen.queryByText('⬇ 3,3 GB')).toBeNull()
  expect(screen.getByText('✓ aktiv — 1 Modelle')).toBeInTheDocument()

  fireEvent.click(screen.getByText('🗑 LÖSCHEN'))
  expect(confirm).toHaveBeenCalled()
  expect(fetch.mock.calls.some(([u]) => String(u) === '/api/ollama/delete')).toBe(false)
})
