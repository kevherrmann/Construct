// Ablauf-Tests der Mail-Ansicht gegen ein nachgebautes Backend (Antworten wie
// mail.py sie liefert). Echte Konten gibt es in der Testumgebung nicht.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import type { MailAccount, MailMessage, MailSummary } from '@/api/mail'
import { initI18n } from '@/lib/i18n'
import { MailMain } from './MailMain'
import { MailSide } from './MailSide'
import { useMailStore } from './mailStore'

initI18n('de')

const ACC_GMX: MailAccount = {
  email: 'kevin@gmx.de',
  provider: 'GMX',
  auth: 'password',
  hint: 'GMX-Webmail → Einstellungen → POP3/IMAP → „Zugriff erlauben“ aktivieren. Dann hier das normale GMX-Passwort eintragen.',
  configured: true,
}
const ACC_MS: MailAccount = {
  email: 'kevin@outlook.de',
  provider: 'Outlook/Hotmail',
  auth: 'oauth',
  hint: 'Microsoft erlaubt kein Passwort-IMAP mehr — einfach auf MICROSOFT-LOGIN klicken und den angezeigten Code auf der Microsoft-Seite eingeben.',
  configured: false,
}

const summary = (p: Partial<MailSummary>): MailSummary => ({
  account: ACC_GMX.email,
  folder: 'INBOX',
  uid: '1',
  key: '<id1@x>',
  from_name: 'Anna Beispiel',
  from_addr: 'anna@beispiel.de',
  to: 'kevin@gmx.de',
  subject: 'Hallo',
  ts: 1758800000,
  seen: true,
  category: '',
  ...p,
})

const MSGS = [
  summary({ uid: '11', key: '<a@x>', subject: 'Angebot', seen: false }),
  summary({ uid: '12', key: '<b@x>', subject: 'Rechnung 42', category: '🧾 Rechnungen' }),
  summary({ uid: '13', key: '<c@x>', subject: 'Treffen', from_name: 'Bob', from_addr: 'bob@y.de' }),
]

const FULL: MailMessage = {
  account: ACC_GMX.email,
  folder: 'INBOX',
  uid: '11',
  key: '<a@x>',
  message_id: '<a@x>',
  from_name: 'Anna Beispiel',
  from_addr: 'anna@beispiel.de',
  to: 'kevin@gmx.de',
  cc: '',
  subject: 'Angebot',
  ts: 1758800000,
  text: 'Zeile 1\nZeile 2',
  html: '<p id="evil">Hallo <script>window.pwned=1</script></p>',
  attachments: [{ idx: 3, name: 'angebot.pdf', size: 2048, mime: 'application/pdf' }],
}

type Handler = (url: URL, init: RequestInit | undefined) => unknown
let routes: Record<string, Handler>
let calls: { path: string; method: string; body: unknown }[]

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

function backend(over: Record<string, Handler> = {}) {
  routes = {
    'GET /api/mail/accounts': () => ({ accounts: [ACC_GMX] }),
    'GET /api/mail/categories': () => ({
      categories: ['📌 Wichtig', '🧾 Rechnungen', '📰 Newsletter', '👨‍👩‍👧 Privat'],
    }),
    'GET /api/mail/list': () => ({ messages: MSGS, errors: {} }),
    'GET /api/mail/msg': () => FULL,
    ...over,
  }
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input, 'http://x')
      const method = init?.method ?? 'GET'
      const body =
        typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : (init?.body ?? null)
      calls.push({ path: url.pathname + url.search, method, body })
      const h = routes[`${method} ${url.pathname}`]
      if (!h) return json({ error: 'nicht gemockt' }, 404)
      const r = h(url, init)
      return r instanceof Response ? r : json(r)
    }),
  )
}

let loc = ''
function Where() {
  const l = useLocation()
  useEffect(() => {
    loc = l.pathname + l.search
  }, [l])
  return null
}

function renderMail(path = '/mail') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/:view/*"
            element={
              <>
                <Where />
                <aside data-testid="side">
                  <MailSide />
                </aside>
                <main data-testid="main">
                  <MailMain />
                </main>
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const main = () => within(screen.getByTestId('main'))
const side = () => within(screen.getByTestId('side'))

beforeEach(() => {
  useMailStore.setState({ filter: { acc: '', cat: '', q: '' }, sel: new Set(), draft: {} })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  vi.spyOn(window, 'alert').mockImplementation(() => {})
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Einrichtung', () => {
  it('ohne Konto geht es direkt zu den Konten; hinzufügen ruft den Server', async () => {
    let accounts: MailAccount[] = []
    backend({
      'GET /api/mail/accounts': () => ({ accounts }),
      'POST /api/mail/accounts': () => {
        accounts = [{ ...ACC_MS }]
        return { ok: true }
      },
    })
    renderMail()
    expect(await main().findByText('⚙ E-MAIL-KONTEN')).toBeInTheDocument()
    expect(loc).toBe('/mail/accounts')
    // Kein Listenabruf ohne eingerichtetes Konto
    expect(calls.some((c) => c.path.startsWith('/api/mail/list'))).toBe(false)

    fireEvent.click(main().getByText('HINZUFÜGEN'))
    expect(main().getByText('⚠ Adresse fehlt')).toBeInTheDocument()

    fireEvent.change(main().getByPlaceholderText('neue@adresse.de'), {
      target: { value: ' kevin@outlook.de ' },
    })
    fireEvent.click(main().getByText('HINZUFÜGEN'))
    expect(await main().findByText('kevin@outlook.de')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      email: 'kevin@outlook.de',
      password: '',
    })
    expect(main().getByText('🔑 MICROSOFT-LOGIN')).toBeInTheDocument()
    expect(main().getByText('— noch nicht eingerichtet')).toBeInTheDocument()

    // ← Posteingang zeigt danach die (leere) Liste, statt wieder umzuleiten.
    fireEvent.click(main().getByText('← Posteingang'))
    expect(await main().findByText('Noch nichts geladen.')).toBeInTheDocument()
  })

  it('Microsoft-Login zeigt Code und fragt nach, bis verbunden', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let polls = 0
    backend({
      'GET /api/mail/accounts': () => ({ accounts: [ACC_MS] }),
      'POST /api/mail/ms_login': () => ({
        url: 'https://microsoft.com/devicelogin',
        code: 'ABC123',
      }),
      'GET /api/mail/ms_poll': () => (++polls < 2 ? { pending: true } : { ok: true }),
    })
    renderMail('/mail/accounts')
    fireEvent.click(await main().findByText('🔑 MICROSOFT-LOGIN'))
    expect(await main().findByText('ABC123')).toBeInTheDocument()
    expect(main().getByRole('link', { name: 'https://microsoft.com/devicelogin' })).toHaveAttribute(
      'target',
      '_blank',
    )
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(polls).toBe(1)
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(await main().findByText('✅ verbunden!')).toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(15000))
    expect(polls).toBe(2) // nach Erfolg kein weiteres Nachfragen
    vi.useRealTimers()
  })

  it('/mail/accounts ist direkt erreichbar (Link aus den Einstellungen)', async () => {
    backend()
    renderMail('/mail/accounts')
    expect(await main().findByText('✓ eingerichtet')).toBeInTheDocument()
    fireEvent.change(main().getByLabelText('kevin@gmx.de'), { target: { value: 'geheim' } })
    routes['POST /api/mail/accounts'] = () => ({ ok: true })
    routes['POST /api/mail/test'] = () => ({ ok: true, inbox: 1234 })
    fireEvent.click(main().getByText('SPEICHERN'))
    expect(await main().findByText('✓ gespeichert — jetzt TEST klicken')).toBeInTheDocument()
    fireEvent.click(main().getByText('TEST'))
    expect(
      await main().findByText('✅ funktioniert — 1234 Mails im Posteingang'),
    ).toBeInTheDocument()
  })
})

describe('Liste', () => {
  it('zeigt Posteingang, Zähler, Suche und Kategoriefilter', async () => {
    backend()
    renderMail()
    expect(await main().findByText('Angebot')).toBeInTheDocument()
    expect(main().getByText('Treffen')).toBeInTheDocument()
    // Kategorisierte Mail lebt nur in ihrer Kategorie
    expect(main().queryByText('Rechnung 42')).toBeNull()
    expect(main().getByText('2 Mails')).toBeInTheDocument()
    expect(main().getByText('● Anna Beispiel')).toBeInTheDocument() // ungelesen

    // Seitenleiste: 1 ungelesen, 2 ohne Kategorie, 1 in Rechnungen
    const all = side().getByText('Alle Postfächer').parentElement!
    expect(all).toHaveTextContent('1')
    expect(side().getByText('Posteingang').parentElement!).toHaveTextContent('2')

    // Suche geht über alle Kategorien
    fireEvent.change(main().getByPlaceholderText('🔎 Suchen … (Absender, Betreff)'), {
      target: { value: 'rechnung' },
    })
    expect(main().getByText('Rechnung 42')).toBeInTheDocument()
    expect(main().queryByText('Angebot')).toBeNull()

    fireEvent.change(main().getByPlaceholderText('🔎 Suchen … (Absender, Betreff)'), {
      target: { value: '' },
    })
    fireEvent.click(side().getByText('🧾 Rechnungen'))
    expect(main().getByText('Rechnung 42')).toBeInTheDocument()
    expect(main().queryByText('Treffen')).toBeNull()
    fireEvent.click(main().getByTitle('Filter aufheben'))
    expect(main().getByText('Treffen')).toBeInTheDocument()
  })

  it('zeigt Kontofehler und markiert das Konto', async () => {
    backend({
      'GET /api/mail/list': () => ({
        messages: [],
        errors: { 'kevin@gmx.de': 'Login fehlgeschlagen: x' },
      }),
    })
    renderMail()
    expect(await main().findByText(/Login fehlgeschlagen: x/)).toBeInTheDocument()
    expect(side().getByText('kevin ⚠')).toBeInTheDocument()
    expect(main().getByText('Keine E-Mails.')).toBeInTheDocument()
  })

  it('AKTUALISIEREN holt mit force=1', async () => {
    backend()
    renderMail()
    await main().findByText('Angebot')
    fireEvent.click(main().getByText('⟲ AKTUALISIEREN'))
    await main().findByText('Angebot')
    expect(calls.some((c) => c.path === '/api/mail/list?limit=9999&force=1')).toBe(true)
  })

  it('Sammel-Löschen: markieren, bestätigen, Teilfehler bleiben stehen', async () => {
    const MIXED = [
      ...MSGS,
      summary({ uid: '99', key: '<z@x>', account: 'k@gmail.com', subject: 'Gmail-Mail' }),
    ]
    backend({
      'GET /api/mail/list': () => ({ messages: MIXED, errors: {} }),
      'POST /api/mail/delete_many': () => ({
        ok: false,
        deleted: 2,
        errors: { 'k@gmail.com': 'Ordner INBOX nicht wählbar' },
      }),
    })
    renderMail()
    await main().findByText('Angebot')
    fireEvent.click(main().getByText('☑ ALLE MARKIEREN'))
    expect(main().getByText('☒ KEINE MARKIEREN')).toBeInTheDocument()
    fireEvent.click(main().getByText('🗑 LÖSCHEN (3)'))
    await waitFor(() => expect(main().queryByText('Angebot')).toBeNull())
    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringMatching(/^3 E-Mail\(s\) wirklich löschen\?/),
    )
    const del = calls.find((c) => c.path === '/api/mail/delete_many')!
    expect(del.body).toEqual({
      items: [
        { account: 'kevin@gmx.de', uid: '11', folder: 'INBOX' },
        { account: 'kevin@gmx.de', uid: '13', folder: 'INBOX' },
        { account: 'k@gmail.com', uid: '99', folder: 'INBOX' },
      ],
    })
    // Gmail-Mail schlug fehl → bleibt in Liste und Auswahl
    expect(main().getByText('Gmail-Mail')).toBeInTheDocument()
    expect(main().getByText('🗑 LÖSCHEN (1)')).toBeInTheDocument()
    expect(window.alert).toHaveBeenCalledWith(
      'Teilweise fehlgeschlagen:\nk@gmail.com: Ordner INBOX nicht wählbar',
    )
  })

  it('Sammel-Kategorie weist zu und hebt die Auswahl auf', async () => {
    backend({ 'POST /api/mail/categorize_many': () => ({ ok: true, count: 1 }) })
    renderMail()
    const row = (await main().findByText('Treffen')).closest('[data-testid="mail-row"]')!
    fireEvent.click(within(row as HTMLElement).getByRole('checkbox'))
    fireEvent.change(main().getByTitle('Markierte einer Kategorie zuweisen'), {
      target: { value: '📌 Wichtig' },
    })
    await waitFor(() => expect(main().queryByText('Treffen')).toBeNull())
    expect(calls.find((c) => c.path === '/api/mail/categorize_many')?.body).toEqual({
      keys: ['<c@x>'],
      category: '📌 Wichtig',
    })
    expect(main().queryByTitle('Markierte einer Kategorie zuweisen')).toBeNull()
  })

  it('einzeln löschen über den Mülleimer der Zeile', async () => {
    backend({ 'POST /api/mail/delete': () => ({ ok: true }) })
    renderMail()
    const row = (await main().findByText('Treffen')).closest('[data-testid="mail-row"]')!
    fireEvent.click(within(row as HTMLElement).getByTitle('löschen (auch auf dem Server)'))
    await waitFor(() => expect(main().queryByText('Treffen')).toBeNull())
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('„Treffen“'))
    expect(loc).toBe('/mail')
  })
})

describe('Lesen und Schreiben', () => {
  it('HTML-Mail nur im Sandbox-iframe; Anhang als Download-Link; gelesen', async () => {
    backend()
    const { container } = renderMail()
    fireEvent.click(await main().findByText('Angebot'))
    expect(await main().findByText('Von:', { exact: false })).toBeInTheDocument()
    expect(loc).toBe('/mail/msg?account=kevin%40gmx.de&uid=11&folder=INBOX')

    const frame = container.querySelector('iframe')!
    expect(frame.getAttribute('sandbox')).toBe('allow-popups allow-popups-to-escape-sandbox')
    expect(frame.getAttribute('srcdoc')).toMatch(/^<base target="_blank">/)
    expect(frame.getAttribute('srcdoc')).toContain('<p id="evil">')
    // Mail-HTML landet NIE im App-DOM
    expect(container.querySelector('#evil')).toBeNull()

    const att = main()
      .getByText(/angebot\.pdf/)
      .closest('a')!
    expect(att.getAttribute('href')).toBe(
      '/api/mail/att?account=kevin%40gmx.de&uid=11&folder=INBOX&idx=3',
    )
    expect(att).toHaveTextContent('(2 kB)')
    // Seitenleiste: nichts mehr ungelesen
    await waitFor(() =>
      expect(side().getByText('Alle Postfächer').parentElement!).toHaveTextContent(
        /^📥 Alle Postfächer$/,
      ),
    )
  })

  it('Textmail ohne HTML als Text; Kategorie und ungelesen', async () => {
    backend({
      'GET /api/mail/msg': () => ({ ...FULL, html: '', attachments: [] }),
      'POST /api/mail/categorize': () => ({ ok: true }),
      'POST /api/mail/flag': () => ({ ok: true }),
    })
    const { container } = renderMail('/mail/msg?account=kevin%40gmx.de&uid=11&folder=INBOX')
    expect(await main().findByText(/Zeile 1/)).toBeInTheDocument()
    expect(container.querySelector('iframe')).toBeNull()

    fireEvent.change(main().getByTitle('Kategorie (nur lokal, nicht beim Anbieter)'), {
      target: { value: '📌 Wichtig' },
    })
    await waitFor(() =>
      expect(calls.find((c) => c.path === '/api/mail/categorize')?.body).toEqual({
        key: '<a@x>',
        category: '📌 Wichtig',
      }),
    )
    fireEvent.click(main().getByText('✉ UNGELESEN'))
    await waitFor(() => expect(loc).toBe('/mail'))
    expect(calls.find((c) => c.path === '/api/mail/flag')?.body).toEqual({
      account: 'kevin@gmx.de',
      uid: '11',
      folder: 'INBOX',
      seen: false,
    })
  })

  it('Fehler beim Laden der Mail wird angezeigt', async () => {
    backend({ 'GET /api/mail/msg': () => json({ error: 'Nachricht nicht (mehr) gefunden' }, 400) })
    renderMail('/mail/msg?account=kevin%40gmx.de&uid=11&folder=INBOX')
    expect(await main().findByText('⚠ Nachricht nicht (mehr) gefunden')).toBeInTheDocument()
  })

  it('Antworten: vorbelegt, Anhang hochladen, senden', async () => {
    backend({
      'POST /api/mail/attach': (_u, init) => {
        const f = (init!.body as FormData).get('file') as File
        return { path: '/srv/mail_attach/abc/' + f.name, name: f.name, size: f.size }
      },
      'POST /api/mail/send': () => ({ ok: true }),
    })
    renderMail('/mail/msg?account=kevin%40gmx.de&uid=11&folder=INBOX')
    fireEvent.click(await main().findByText('↩ ANTWORTEN'))
    expect(await main().findByText('✉ ANTWORT')).toBeInTheDocument()
    expect(main().getByLabelText('AN')).toHaveValue('anna@beispiel.de')
    expect(main().getByLabelText('BETREFF')).toHaveValue('Re: Angebot')
    const body = (main().getByLabelText('NACHRICHT') as HTMLTextAreaElement).value
    expect(body).toMatch(/^\n\nAm .+ schrieb Anna Beispiel:\n> Zeile 1\n> Zeile 2$/)

    const file = new File(['%PDF'], 'plan.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByTestId('mc-file'), { target: { files: [file] } })
    expect(await main().findByText(/plan\.pdf/)).toBeInTheDocument()

    fireEvent.click(main().getByText('➤ SENDEN'))
    expect(await main().findByText('✅ gesendet!')).toBeInTheDocument()
    expect(calls.find((c) => c.path === '/api/mail/send')?.body).toEqual({
      account: 'kevin@gmx.de',
      to: 'anna@beispiel.de',
      cc: '',
      subject: 'Re: Angebot',
      body,
      attachments: [{ path: '/srv/mail_attach/abc/plan.pdf', name: 'plan.pdf' }],
      reply: '<a@x>',
    })
    await waitFor(() => expect(loc).toBe('/mail'), { timeout: 2000 })
  })

  it('Neue E-Mail: ohne Empfänger kein Versand; Serverfehler wird gezeigt', async () => {
    backend({ 'POST /api/mail/send': () => json({ error: 'Kein (gültiger) Empfänger' }, 400) })
    renderMail()
    await main().findByText('Angebot')
    fireEvent.click(side().getByText('✉ NEUE E-MAIL'))
    expect(await main().findByText('✉ NEUE E-MAIL')).toBeInTheDocument()
    fireEvent.click(main().getByText('➤ SENDEN'))
    expect(main().getByText('⚠ Empfänger fehlt')).toBeInTheDocument()
    fireEvent.change(main().getByLabelText('AN'), { target: { value: 'kaputt' } })
    fireEvent.click(main().getByText('➤ SENDEN'))
    expect(await main().findByText('⚠ Kein (gültiger) Empfänger')).toBeInTheDocument()
    expect(main().getByText('➤ SENDEN')).not.toBeDisabled()
  })

  it('Weiterleiten übernimmt den Text', async () => {
    backend()
    renderMail('/mail/msg?account=kevin%40gmx.de&uid=11&folder=INBOX')
    fireEvent.click(await main().findByText('↪ WEITERLEITEN'))
    expect(await main().findByLabelText('BETREFF')).toHaveValue('Fwd: Angebot')
    expect(main().getByLabelText('AN')).toHaveValue('')
    expect((main().getByLabelText('NACHRICHT') as HTMLTextAreaElement).value).toMatch(
      /---------- Weitergeleitete Nachricht ----------\nVon: Anna Beispiel <anna@beispiel.de>\nDatum: .+\nBetreff: Angebot\n\nZeile 1/,
    )
  })
})

describe('Kategorien in der Seitenleiste', () => {
  it('anlegen und löschen', async () => {
    let cats = ['📌 Wichtig']
    backend({
      'GET /api/mail/categories': () => ({ categories: cats }),
      'POST /api/mail/categories': (_u, init) => {
        const b = JSON.parse(init!.body as string) as { add?: string; remove?: string }
        if (b.add) cats = [...cats, b.add]
        if (b.remove) cats = cats.filter((c) => c !== b.remove)
        return { categories: cats }
      },
    })
    vi.spyOn(window, 'prompt').mockReturnValue('  Reisen ')
    renderMail()
    await side().findByText('📌 Wichtig')
    fireEvent.click(side().getByTitle('Neue Kategorie anlegen'))
    expect(await side().findByText('Reisen')).toBeInTheDocument()
    const row = side().getByText('Reisen').parentElement!
    fireEvent.click(within(row).getByTitle('Kategorie löschen'))
    await waitFor(() => expect(side().queryByText('Reisen')).toBeNull())
    expect(window.confirm).toHaveBeenCalledWith(
      'Kategorie „Reisen“ löschen? (Die E-Mails bleiben natürlich erhalten.)',
    )
  })
})
