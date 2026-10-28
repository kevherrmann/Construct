import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { initI18n } from '@/lib/i18n'
import { useChat } from '@/stores/chat'
import { dateYMD } from '@/views/calendar/dates'
import { Start } from './Start'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } })

const morgen = () => {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return dateYMD(d)
}

const original = useChat.getState()
beforeAll(() => initI18n('de'))
afterEach(() => {
  useChat.setState(original, true)
  vi.restoreAllMocks()
})

it('zeigt den nächsten Termin, die letzte Session und schickt einen Einstieg', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const u = String(url)
    if (u.startsWith('/api/events'))
      return json([
        {
          id: 'e1',
          date: morgen(),
          time: '10:00',
          title: 'Helpdesk-Test',
          notes: '',
          repeat: '',
          prompt: '',
          created: '',
        },
      ])
    if (u.startsWith('/api/sessions'))
      return json([
        {
          id: 'a',
          project: 'p',
          cwd: '/x',
          title: 'Alte Sache',
          renamed: false,
          mtime: 1,
          archived: false,
          agent: '',
        },
        {
          id: 'b',
          project: 'p',
          cwd: '/x',
          title: 'Neueste Sache',
          renamed: false,
          mtime: 9,
          archived: false,
          agent: '',
        },
      ])
    return json([])
  })
  const send = vi.fn().mockResolvedValue(undefined)
  useChat.setState({ send })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <Start />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(await screen.findByText('Helpdesk-Test')).toBeVisible()
  expect(screen.getByText(/morgen · 10:00/)).toBeVisible()
  expect(await screen.findByText('↻ Weiter mit „Neueste Sache“')).toBeVisible()
  fireEvent.click(screen.getByText(/Was kannst du alles\?/))
  expect(send).toHaveBeenCalledWith('Was kannst du alles für mich tun?')
})
