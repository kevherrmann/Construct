import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { initI18n } from '@/lib/i18n'
import { openDialog, useDialogs } from '@/stores/dialogs'
import { LoginDialog } from './LoginDialog'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

beforeAll(() => {
  initI18n('de')
})
afterEach(() => {
  vi.restoreAllMocks()
  useDialogs.getState().close()
})

function setup() {
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <LoginDialog />
    </QueryClientProvider>,
  )
  act(() => openDialog('login'))
}

it('Start → Link → Code → angemeldet', async () => {
  const fetch = vi
    .spyOn(window, 'fetch')
    .mockResolvedValueOnce(json({ url: 'https://claude.ai/oauth?x=1' }))
    .mockResolvedValueOnce(json({ ok: true }))
  setup()
  fireEvent.click(screen.getByText('LOGIN STARTEN'))
  const link = await screen.findByText('https://claude.ai/oauth?x=1')
  expect(link.getAttribute('href')).toBe('https://claude.ai/oauth?x=1')
  fireEvent.change(screen.getByPlaceholderText('Code hier einfügen'), {
    target: { value: ' abc#123 ' },
  })
  fireEvent.click(screen.getByText('CODE BESTÄTIGEN'))
  expect(await screen.findByText(/Angemeldet!/)).toBeInTheDocument()
  expect(fetch.mock.calls[1]![0]).toBe('/api/auth/code')
  expect(JSON.parse(fetch.mock.calls[1]![1]!.body as string)).toEqual({ code: 'abc#123' })
})

it('zeigt die Fehlermeldung des Servers', async () => {
  vi.spyOn(window, 'fetch').mockResolvedValueOnce(
    json({ error: 'Claude Code ist nicht installiert.' }, 500),
  )
  setup()
  fireEvent.click(screen.getByText('LOGIN STARTEN'))
  expect(await screen.findByText('⚠ Claude Code ist nicht installiert.')).toBeInTheDocument()
  // Nochmal versuchen geht.
  expect(screen.getByText('LOGIN STARTEN')).not.toBeDisabled()
})
