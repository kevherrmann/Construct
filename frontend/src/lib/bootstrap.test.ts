import { readBootstrap, DEFAULT_SETTINGS } from './bootstrap'

describe('readBootstrap', () => {
  it('liefert Vorgaben, wenn der Server nichts eingesetzt hat', () => {
    const b = readBootstrap({})
    expect(b.assistant).toBe('Cody')
    expect(b.lang).toBe('en')
    expect(b.settings.theme).toBe(DEFAULT_SETTINGS.theme)
  })

  it('übernimmt Sprache und Einstellungen vom Server', () => {
    const b = readBootstrap({
      lang: 'de',
      assistant: 'Cody',
      settings: { ...DEFAULT_SETTINGS, theme: 'papier' },
    })
    expect(b.lang).toBe('de')
    expect(b.settings.lang).toBe('de')
    expect(b.settings.theme).toBe('papier')
  })
})
