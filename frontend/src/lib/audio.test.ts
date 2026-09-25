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
  expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string)).toEqual({ text: 'Hallo', voice: 'v' })
  expect(result.current).toEqual({ owner: 'm1', phase: 'playing' })
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
