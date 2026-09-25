import { act, renderHook } from '@testing-library/react'
import { usePolling } from './usePolling'

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

it('fragt nur ab, solange aktiv, und reicht die Daten weiter', async () => {
  let n = 0
  const fetch = vi.fn(async () => ++n)
  const seen: number[] = []
  const { rerender, unmount } = renderHook(
    ({ on }) => usePolling(on, fetch, (d) => seen.push(d), 1000),
    { initialProps: { on: false } },
  )
  await act(() => vi.advanceTimersByTimeAsync(3000))
  expect(fetch).not.toHaveBeenCalled()

  rerender({ on: true })
  await act(() => vi.advanceTimersByTimeAsync(2000))
  expect(seen).toEqual([1, 2])

  rerender({ on: false })
  await act(() => vi.advanceTimersByTimeAsync(3000))
  expect(seen).toEqual([1, 2])
  unmount()
})

it('übergeht einzelne Fehler', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error('weg')).mockResolvedValue('ok')
  const seen: string[] = []
  renderHook(() => usePolling(true, fetch, (d: string) => seen.push(d), 500))
  await act(() => vi.advanceTimersByTimeAsync(1000))
  expect(seen).toEqual(['ok'])
})
