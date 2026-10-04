import { describe, expect, it } from 'vitest'
import {
  aufBuehne,
  GANZ,
  parallelMatrix,
  verschiebung,
  viereckMatrix,
  type Viereck,
} from './kamera'

describe('Kamera', () => {
  it('ganzer Raum: keine Verschiebung', () => {
    expect(verschiebung(GANZ)).toEqual([0, 0])
  })

  it('bringt den Fokuspunkt an die gewünschte Stelle', () => {
    const k = { z: 2, f: [40, 40], p: [50, 50] } as const
    expect(aufBuehne(k, k.f)).toEqual([50, 50])
  })

  it('zeigt am Rand keine Leere', () => {
    // Station ganz rechts: die Kamera bleibt am rechten Rand stehen.
    const [x, y] = verschiebung({ z: 1.6, f: [97, 50], p: [50, 50] })
    expect(x).toBeCloseTo(-60)
    expect(y).toBeLessThanOrEqual(0)
    expect(verschiebung({ z: 1.5, f: [2, 2], p: [50, 50] })).toEqual([0, 0])
  })
})

describe('viereckMatrix', () => {
  // Abbildung nachrechnen wie der Browser: (X, Y, 0, 1) · matrix3d
  const abbilden = (css: string, X: number, Y: number) => {
    const m = css.slice(9, -1).split(',').map(Number)
    const w = m[3]! * X + m[7]! * Y + m[15]!
    return [(m[0]! * X + m[4]! * Y + m[12]!) / w, (m[1]! * X + m[5]! * Y + m[13]!) / w]
  }

  it('legt die Ecken des Rechtecks auf die Ecken des Vierecks', () => {
    const q: Viereck = [
      [100, 50],
      [700, 120],
      [690, 400],
      [105, 330],
    ]
    const css = viereckMatrix(1000, 400, q)
    const ecken = [
      [0, 0],
      [1000, 0],
      [1000, 400],
      [0, 400],
    ] as const
    ecken.forEach(([X, Y], i) => {
      const [x, y] = abbilden(css, X, Y)
      expect(x).toBeCloseTo(q[i]![0], 4)
      expect(y).toBeCloseTo(q[i]![1], 4)
    })
  })
})

describe('parallelMatrix', () => {
  it('legt drei Ecken genau, die vierte folgt als Parallelogramm', () => {
    const m = parallelMatrix(200, 50, [10, 100], [210, 40], [10, 150])
      .slice(7, -1)
      .split(',')
      .map(Number)
    const p = (X: number, Y: number) => [
      m[0]! * X + m[2]! * Y + m[4]!,
      m[1]! * X + m[3]! * Y + m[5]!,
    ]
    expect(p(0, 0)).toEqual([10, 100])
    expect(p(200, 0)).toEqual([210, 40])
    expect(p(0, 50)).toEqual([10, 150])
    expect(p(200, 50)).toEqual([210, 90])
  })
})
