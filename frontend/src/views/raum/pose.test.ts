import { describe, expect, it } from 'vitest'
import type { Lage, Phase } from './lage'
import { zielPose } from './pose'

const lage = (phase: Phase, live = phase !== 'ruht'): Lage => ({
  phase,
  station: null,
  detail: '',
  text: '',
  md: '',
  live,
})

describe('zielPose', () => {
  it('folgt der eigenen Lage, solange die Chefin keinen Zug hat', () => {
    expect(zielPose(lage('ruht'), null)).toBe('idle')
    expect(zielPose(lage('denkt'), null)).toBe('denken')
    expect(zielPose(lage('schreibt'), null)).toBe('arbeiten')
  })

  it('denkt, wenn die Chefin im Firmenzug nachdenkt (Blase: „denkt nach …“)', () => {
    expect(zielPose(lage('ruht'), lage('denkt'))).toBe('denken')
    expect(zielPose(lage('ruht'), lage('wartet'))).toBe('denken')
  })

  it('redet, wenn die Chefin antwortet, abgibt oder fertig ist', () => {
    expect(zielPose(lage('ruht'), lage('antwortet'))).toBe('erklaeren')
    // Bus-Aufrufe (beauftragen, liefern): an die Werkbank geht sie dafür nicht
    expect(zielPose(lage('ruht'), lage('werkzeug'))).toBe('erklaeren')
    expect(zielPose(lage('ruht'), lage('ruht'))).toBe('erklaeren')
  })

  it('liest, wenn sie liest', () => {
    expect(zielPose(lage('ruht'), lage('liest'))).toBe('lesen')
  })

  it('dein eigenes Gespräch geht vor', () => {
    expect(zielPose(lage('schreibt'), lage('denkt'))).toBe('arbeiten')
    expect(zielPose(lage('antwortet'), lage('denkt'))).toBe('erklaeren')
  })
})
