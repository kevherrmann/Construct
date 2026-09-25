import { joinSpoken } from './dictation'

describe('joinSpoken', () => {
  it('hängt die laufende Äußerung an die bereinigten an', () => {
    expect(joinSpoken(['Hallo Cody.', 'Zweiter Satz.'], 'und noch')).toBe(
      'Hallo Cody. Zweiter Satz. und noch',
    )
  })
  it('lässt Leeres weg', () => {
    expect(joinSpoken([], '')).toBe('')
    expect(joinSpoken(['  Eins. '], ' ')).toBe('Eins.')
  })
})
