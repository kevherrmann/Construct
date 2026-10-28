import { abonnieren, RUHE_MS, ruhtJetzt } from './ruhe'

afterEach(() => vi.useRealTimers())

it('ruht nach RUHE_MS ohne Eingabe und wacht bei der Maus wieder auf', () => {
  vi.useFakeTimers()
  const meldungen: boolean[] = []
  const ab = abonnieren(() => meldungen.push(ruhtJetzt()))
  expect(ruhtJetzt()).toBe(false)
  vi.advanceTimersByTime(RUHE_MS + 15_000)
  expect(ruhtJetzt()).toBe(true)
  dispatchEvent(new Event('pointermove'))
  expect(ruhtJetzt()).toBe(false)
  expect(meldungen).toEqual([true, false])
  ab()
})
