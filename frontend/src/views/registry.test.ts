import { VIEWS } from './registry'

// Schutz gegen doppelte Menüpunkte (passiert leicht beim Zusammenführen).
it('jede Ansicht kommt genau einmal vor, in der Reihenfolge des Menüs', () => {
  expect(VIEWS.map((v) => v.key)).toEqual(['chat', 'skills', 'calendar', 'mail', 'mcp', 'settings'])
})
