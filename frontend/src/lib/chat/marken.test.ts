import { ohneMarke } from './marken'

describe('ohneMarke', () => {
  it('entfernt die Markerzeile am Ende, auch halb getippt', () => {
    expect(ohneMarke('Fertig.\n\n[[ticket neu: Kachel bauen]]')).toBe('Fertig.')
    expect(ohneMarke('Fertig.\n\n[[ticket ne')).toBe('Fertig.')
    expect(ohneMarke('Fertig.\n[[')).toBe('Fertig.')
  })
  it('lässt Text ohne Marker und Marker mitten im Text in Ruhe', () => {
    expect(ohneMarke('Nichts davon.')).toBe('Nichts davon.')
    expect(ohneMarke('Beispiel [[ticket neu: X]] mitten drin.\nEnde.')).toBe(
      'Beispiel [[ticket neu: X]] mitten drin.\nEnde.',
    )
  })
})
