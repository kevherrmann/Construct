import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useBuero } from './useBuero'

// Belegschaft und Stand kommen per Abfrage, also erst nach dem ersten Zeichnen.
const daten = vi.hoisted(() => ({
  bel: undefined as unknown,
  stand: undefined as unknown,
}))
vi.mock('@/api/team', () => ({
  useTeamAn: () => true,
  useBelegschaft: () => ({ data: daten.bel }),
  useTeamStand: () => ({ data: daten.stand }),
}))

const agent = (slug: string) => ({ slug, name: slug, status: 'active', color: '1, 2, 3' })
const BEL = { agents: [agent('chef'), agent('luna'), agent('miranda')] }
const stand = (...slugs: string[]) => ({
  aktiv: slugs.map((agent) => ({ agent, name: agent, color: '', ticket: 't', titel: '', seit: 0 })),
  wartend: [],
  pausiert: false,
})

describe('useBuero', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    daten.bel = undefined
    daten.stand = undefined
  })
  afterEach(() => vi.useRealTimers())

  it('kein Besuch für den, der beim Laden schon arbeitet', () => {
    const { result, rerender } = renderHook(() => useBuero(true))
    daten.bel = BEL
    daten.stand = stand('luna')
    rerender()
    act(() => vi.advanceTimersByTime(100))
    expect(result.current?.besuch).toBeNull()
    expect(result.current?.werk).toBe('luna')
  })

  it('Besuch, wenn danach jemand neu anfängt', () => {
    daten.bel = BEL
    daten.stand = stand()
    const { result, rerender } = renderHook(() => useBuero(true))
    daten.stand = stand('miranda')
    rerender()
    expect(result.current?.besuch).toMatchObject({ slug: 'miranda' })
  })
})
