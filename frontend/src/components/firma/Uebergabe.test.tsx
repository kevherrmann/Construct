import { Fragment } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Uebergabe } from '@/api/team'
import { initI18n } from '@/lib/i18n'
import { useSettings } from '@/stores/settings'
import { useFirmaImChat } from './FirmaImChat'
import { UebergabeHinweis } from './Uebergabe'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })

/** Antwort auf alles andere (Team-Chat, Stand), sobald die Firma an ist. */
const LEER = { auftraege: [], agents: {}, aktiv: [] }

const offen = (id: string, titel: string, erstellt = 100): Uebergabe => ({
  id,
  titel,
  status: 'offen',
  erstellt,
  auftrag: null,
})

const mitQuery = (node: React.ReactNode) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {node}
    </QueryClientProvider>,
  )

/** Was useFirmaImChat in den Chat einsortiert, in seiner Reihenfolge. */
function Zeilen({ sid }: { sid: string }) {
  const { zeilen } = useFirmaImChat(sid)
  return (
    <div>
      {zeilen.map((z) => (
        <Fragment key={z.key}>{z.node}</Fragment>
      ))}
    </div>
  )
}

beforeAll(() => initI18n('de'))
beforeEach(() => {
  const st = useSettings.getState()
  useSettings.setState({
    settings: { ...st.settings, team: { ...st.settings.team, aktiv: false } },
  })
})
afterEach(() => vi.restoreAllMocks())

it('offen: sagt, dass nichts ankam, und bietet den Knopf an', () => {
  mitQuery(<UebergabeHinweis sid="s1" u={offen('e1', 'Regal umbauen')} />)
  expect(screen.getByText('Die Firma ist aus, der Auftrag ist nicht angekommen')).toBeVisible()
  expect(screen.getByText('Regal umbauen')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Firma einschalten und übergeben' })).toBeEnabled()
})

it('übergeben: nur noch eine leise Zeile, kein Knopf', () => {
  mitQuery(
    <UebergabeHinweis
      sid="s1"
      u={{ ...offen('e1', 'Regal umbauen'), status: 'uebergeben', auftrag: 'a1' }}
    />,
  )
  expect(screen.getByText(/an die Firma übergeben/)).toHaveTextContent('Regal umbauen')
  expect(screen.queryByRole('button')).toBeNull()
})

it('Knopf: übergibt an genau diese Session und schaltet den Team-Schalter ein', async () => {
  const fetch = vi.spyOn(window, 'fetch').mockImplementation(async (u, init) => {
    const url = String(u)
    if (url === '/api/firma/uebergaben/s1' && !init?.method)
      return json({ uebergaben: [offen('e1', 'Regal umbauen')] })
    if (url === '/api/firma/uebergaben/s1/e1' && init?.method === 'POST')
      return json({
        ok: true,
        uebergabe: { ...offen('e1', 'Regal umbauen'), status: 'uebergeben', auftrag: 'a1' },
        auftrag: 'a1',
        settings: { ...useSettings.getState().settings, team: { aktiv: true } },
      })
    return json(LEER)
  })
  mitQuery(<Zeilen sid="s1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Firma einschalten und übergeben' }))
  expect(await screen.findByText(/an die Firma übergeben/)).toBeVisible()
  expect(screen.queryByRole('button')).toBeNull()
  expect(useSettings.getState().settings.team.aktiv).toBe(true)
  expect(fetch).toHaveBeenCalledWith(
    '/api/firma/uebergaben/s1/e1',
    expect.objectContaining({ method: 'POST' }),
  )
})

it('nach dem Neuladen: alle Übergaben der Session kommen zurück, älteste zuerst', async () => {
  vi.spyOn(window, 'fetch').mockImplementation(async (u) =>
    String(u) === '/api/firma/uebergaben/s1'
      ? json({
          uebergaben: [
            offen('e1', 'Erster Auftrag', 100),
            { ...offen('e2', 'Zweiter Auftrag', 200), status: 'uebergeben', auftrag: 'a2' },
            offen('e3', 'Dritter Auftrag', 300),
          ],
        })
      : json(LEER),
  )
  const { container } = mitQuery(<Zeilen sid="s1" />)
  await screen.findByText('Erster Auftrag')
  expect(screen.getAllByRole('button')).toHaveLength(2)
  const text = container.textContent!
  expect(text.indexOf('Erster')).toBeLessThan(text.indexOf('Zweiter'))
  expect(text.indexOf('Zweiter')).toBeLessThan(text.indexOf('Dritter'))
})

it('409 (schon übergeben, etwa im anderen Fenster): holt den Stand neu', async () => {
  let uebergeben = false
  vi.spyOn(window, 'fetch').mockImplementation(async (u, init) => {
    const url = String(u)
    if (url === '/api/firma/uebergaben/s1/e1') {
      uebergeben = true
      return json({ error: 'Nichts offen.', uebergaben: [] }, 409)
    }
    if (url === '/api/firma/uebergaben/s1' && !init?.method)
      return json({
        uebergaben: [
          uebergeben
            ? { ...offen('e1', 'Regal umbauen'), status: 'uebergeben', auftrag: 'a1' }
            : offen('e1', 'Regal umbauen'),
        ],
      })
    return json(LEER)
  })
  mitQuery(<Zeilen sid="s1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Firma einschalten und übergeben' }))
  expect(await screen.findByText(/an die Firma übergeben/)).toBeVisible()
  expect(screen.queryByRole('button')).toBeNull()
})

it('400: der Fehler steht im Hinweis, der Knopf bleibt', async () => {
  vi.spyOn(window, 'fetch').mockImplementation(async (u, init) => {
    const url = String(u)
    if (url === '/api/firma/uebergaben/s1/e1')
      return json({ error: 'Der Arbeitsordner fehlt.' }, 400)
    if (url === '/api/firma/uebergaben/s1' && !init?.method)
      return json({ uebergaben: [offen('e1', 'Regal umbauen')] })
    return json(LEER)
  })
  mitQuery(<Zeilen sid="s1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Firma einschalten und übergeben' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Der Arbeitsordner fehlt.')
  // der Server hat die Firma trotzdem eingeschaltet
  expect(useSettings.getState().settings.team.aktiv).toBe(true)
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Firma einschalten und übergeben' })).toBeEnabled(),
  )
})
