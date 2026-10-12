import { say, stopSay, useSayState } from './audio'
import { renderHook, act } from '@testing-library/react'

class FakeAudio {
  static last: FakeAudio | null = null
  onended: (() => void) | null = null
  paused = true
  constructor(readonly src: string) {
    FakeAudio.last = this
  }
  play() {
    this.paused = false
    return Promise.resolve()
  }
  pause() {
    this.paused = true
  }
}

beforeEach(() => {
  vi.stubGlobal('Audio', FakeAudio)
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => {
  stopSay()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

it('spielt, meldet den Zustand und räumt am Ende auf', async () => {
  const fetch = vi.spyOn(window, 'fetch').mockResolvedValue(new Response('RIFF'))
  const { result } = renderHook(() => useSayState())
  await act(() => say('Hallo', { owner: 'm1', voice: 'v' }))
  expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string)).toEqual({
    text: 'Hallo',
    voice: 'v',
    teil: 0,
  })
  expect(result.current).toEqual({ owner: 'm1', phase: 'playing', error: null })
  act(() => FakeAudio.last!.onended!())
  expect(result.current.phase).toBe('idle')
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:x')
})

it('wirft die Meldung des Servers', async () => {
  vi.spyOn(window, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ error: 'Kein Gemini-Key' }), { status: 400 }),
  )
  await expect(say('x')).rejects.toThrow('Kein Gemini-Key')
})

it('ein neuer Start verdrängt den alten', async () => {
  let release!: (r: Response) => void
  vi.spyOn(window, 'fetch')
    .mockReturnValueOnce(new Promise((r) => (release = r)))
    .mockResolvedValueOnce(new Response('b'))
  const first = say('eins', { owner: 'a' })
  await say('zwei', { owner: 'b' })
  release(new Response('a'))
  await first
  const { result } = renderHook(() => useSayState())
  expect(result.current.owner).toBe('b')
})

// Antwort wie vom Server: WAV-Stück + Kopfzeile mit der Zahl der Stücke.
const stueck = (inhalt: string, teile: number) =>
  new Response(inhalt, { headers: { 'X-TTS-Teile': String(teile) } })
const teilVon = (call: unknown[]) =>
  (JSON.parse((call[1] as RequestInit).body as string) as { teil: number }).teil

it('lokale Stimme: spielt Stück für Stück und holt das nächste schon vorher', async () => {
  const fetch = vi.spyOn(window, 'fetch').mockImplementation(() => Promise.resolve(stueck('x', 3)))
  const { result } = renderHook(() => useSayState())
  await act(() => say('lang', { owner: 'm' }))
  // Stück 0 spielt, Stück 1 ist schon unterwegs.
  expect(fetch.mock.calls.map(teilVon)).toEqual([0, 1])
  const erstes = FakeAudio.last
  await act(async () => erstes!.onended!())
  expect(FakeAudio.last).not.toBe(erstes)
  expect(fetch.mock.calls.map(teilVon)).toEqual([0, 1, 2])
  expect(result.current.phase).toBe('playing')
  await act(async () => FakeAudio.last!.onended!())
  await act(async () => FakeAudio.last!.onended!())
  expect(result.current.phase).toBe('idle')
  expect(fetch).toHaveBeenCalledTimes(3)
})

it('lokale Stimme: Stopp beendet auch die folgenden Stücke', async () => {
  const fetch = vi.spyOn(window, 'fetch').mockImplementation(() => Promise.resolve(stueck('x', 5)))
  await act(() => say('lang', { owner: 'm' }))
  const erstes = FakeAudio.last
  act(() => stopSay())
  await act(async () => erstes!.onended!())
  expect(FakeAudio.last).toBe(erstes)
  expect(fetch.mock.calls.map(teilVon)).toEqual([0, 1])
})

it('lokale Stimme: ein späteres Stück scheitert → ⚠ am Knopf, kein Wurf', async () => {
  vi.spyOn(window, 'fetch')
    .mockResolvedValueOnce(stueck('a', 2))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'Zu wenig Grafikspeicher' }), { status: 400 }),
    )
  const { result } = renderHook(() => useSayState())
  await act(() => say('lang', { owner: 'm' }))
  await act(async () => FakeAudio.last!.onended!())
  expect(result.current.phase).toBe('idle')
  expect(result.current.error).toEqual({ owner: 'm', message: 'Zu wenig Grafikspeicher' })
})

it('Stopp während das erste Stück lädt: kein ⚠ und kein Fehler', async () => {
  let antworte!: (r: Response) => void
  vi.spyOn(window, 'fetch').mockReturnValueOnce(new Promise((r) => (antworte = r)))
  const { result } = renderHook(() => useSayState())
  const laeuft = say('lang', { owner: 'm' })
  act(() => stopSay())
  antworte(
    new Response(JSON.stringify({ error: 'Die lokale Stimme wurde gestoppt.' }), { status: 400 }),
  )
  await expect(laeuft).resolves.toBeUndefined()
  expect(result.current).toEqual({ owner: null, phase: 'idle', error: null })
})
