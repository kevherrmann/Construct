import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { CalEvent } from '@/api/calendar'
import { initI18n } from '@/lib/i18n'
import { useChat } from '@/stores/chat'
import { AntwortId } from './antwortId'
import { RichMarkdown } from './GenUi'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } })

const mitQuery = (node: React.ReactNode) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {node}
    </QueryClientProvider>,
  )

const ui = (spec: unknown) => '```ui\n' + JSON.stringify(spec) + '\n```'
const WAHL = ui({ type: 'choices', question: 'Wie weiter?', options: ['Testen', 'Committen'] })
const TERMIN = ui({ type: 'event', title: 'Zahnarzt', date: '2026-11-03', time: '09:30' })

const original = useChat.getState()
beforeAll(() => initI18n('de'))
afterEach(() => {
  useChat.setState(original, true)
  vi.restoreAllMocks()
})

it('Antwort-Buttons schicken die Wahl und sperren danach', () => {
  const send = vi.fn().mockResolvedValue(undefined)
  useChat.setState({ send })
  mitQuery(<RichMarkdown text={`Was jetzt?\n\n${WAHL}`} />)
  expect(screen.getByText('Was jetzt?')).toBeVisible()
  expect(screen.getByText('Wie weiter?')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Committen' }))
  expect(send).toHaveBeenCalledWith('Committen', { hinten: true })
  expect(screen.getByRole('button', { name: '✓ Committen' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Testen' })).toBeDisabled()
})

it('nach dem Neuladen zeigt die nächste Eingabe, was gewählt wurde', () => {
  useChat.setState({
    active: () =>
      ({
        history: [
          { kind: 'bot', id: 'b1' },
          { kind: 'user', id: 'u1', text: 'Testen' },
        ],
      }) as unknown as ReturnType<typeof original.active>,
  })
  mitQuery(
    <AntwortId.Provider value="b1">
      <RichMarkdown text={WAHL} />
    </AntwortId.Provider>,
  )
  expect(screen.getByRole('button', { name: '✓ Testen' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Committen' })).toBeDisabled()
})

it('Terminkarte trägt den Termin ein', async () => {
  const calls: { method: string; body: unknown }[] = []
  let events: Partial<CalEvent>[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      calls.push({ method: 'POST', body })
      events = [{ id: 'e1', ...body }]
      return json(events[0])
    }
    return json(events)
  })
  mitQuery(<RichMarkdown text={TERMIN} />)
  expect(screen.getByText('Zahnarzt')).toBeVisible()
  const knopf = await screen.findByRole('button', { name: 'Eintragen' })
  await waitFor(() => expect(knopf).toBeEnabled())
  fireEvent.click(knopf)
  await screen.findByText('✓ Im Kalender')
  expect(calls[0]?.body).toMatchObject({ date: '2026-11-03', time: '09:30', title: 'Zahnarzt' })
})

it('ein offener Baustein beim Streamen zeigt einen Platzhalter statt JSON', () => {
  mitQuery(<RichMarkdown text={'Moment:\n```ui\n{"type":"cho'} streaming />)
  expect(screen.getByText('baue Karte …')).toBeVisible()
  expect(screen.queryByText(/"type"/)).toBeNull()
})

it('Formular schickt alle Felder als eine Nachricht und sperrt danach', () => {
  const send = vi.fn().mockResolvedValue(undefined)
  useChat.setState({ send })
  const form = ui({
    type: 'form',
    title: 'Kunde',
    fields: [
      { label: 'Firma', required: true },
      { label: 'Priorität', type: 'select', options: ['hoch', 'normal'] },
    ],
  })
  mitQuery(<RichMarkdown text={form} />)
  fireEvent.change(screen.getByLabelText(/Firma/), { target: { value: 'Müller' } })
  fireEvent.change(screen.getByLabelText('Priorität'), { target: { value: 'hoch' } })
  fireEvent.click(screen.getByRole('button', { name: 'Absenden' }))
  expect(send).toHaveBeenCalledWith('**Kunde**\nFirma: Müller\nPriorität: hoch', { hinten: true })
  expect(screen.getByText('✓ Abgeschickt')).toBeVisible()
  expect(screen.getByLabelText(/Firma/)).toBeDisabled()
})

it('Checkliste zeigt Fortschritt und Fehlschläge', () => {
  const liste = ui({
    type: 'checklist',
    title: 'Helpdesk-Test',
    items: [{ text: 'Ticket anlegen', state: 'done' }, { text: 'Mail', state: 'failed' }, 'Portal'],
  })
  mitQuery(<RichMarkdown text={liste} />)
  expect(screen.getByText('Helpdesk-Test')).toBeVisible()
  expect(screen.getByText('1/3 · 1 fehlgeschlagen')).toBeVisible()
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1')
})

it('Diagramm zeichnet Balken, zeigt den Wert beim Überfahren und hat eine Tabelle', () => {
  const chart = ui({
    type: 'chart',
    title: 'Tickets pro Woche',
    labels: ['KW40', 'KW41'],
    values: [3, 1200],
  })
  const { container } = mitQuery(<RichMarkdown text={chart} />)
  expect(container.querySelectorAll('svg path')).toHaveLength(2)
  fireEvent.pointerEnter(screen.getByLabelText('KW41: 1.200'))
  expect(screen.getAllByText('1.200').length).toBeGreaterThan(0)
  fireEvent.click(screen.getByRole('button', { name: 'Tabelle' }))
  expect(screen.getByRole('table')).toBeVisible()
  expect(screen.getByRole('cell', { name: '3' })).toBeVisible()
})
