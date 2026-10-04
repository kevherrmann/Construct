import en from '@/i18n/en.json'
import { SECTIONS, navLabel } from './sections'

it('navLabel wie in der alten Oberfläche', () => {
  expect(navLabel('🧠 MODELLE & ANBIETER')).toBe('Modelle & Anbieter')
  expect(navLabel('📧 E-MAIL-KONTEN')).toBe('E-Mail-Konten')
  expect(navLabel('✈ TELEGRAM')).toBe('Telegram')
})

// Überschriften und Menüeinträge stehen nicht in t('…')-Literalen — der
// allgemeine Übersetzungstest sieht sie nicht.
it('Überschriften und Menü sind übersetzt', () => {
  const dict = en as Record<string, string>
  const missing = SECTIONS.flatMap((s) => [s.title, navLabel(s.title)]).filter((k) => !(k in dict))
  expect(missing).toEqual([])
})

it('jeder Abschnitt steht in genau einem Tab', async () => {
  const { TABS } = await import('./sections')
  const ids = TABS.flatMap((x) => [...x.sections])
  expect([...ids].sort()).toEqual(SECTIONS.map((x) => x.id).sort())
  expect(new Set(ids).size).toBe(ids.length)
})

it('Tab aus der Adresse: Tab-Name oder Abschnitt', async () => {
  const { tabAus } = await import('./sections')
  expect(tabAus('system')).toBe('system')
  expect(tabAus('telegram')).toBe('verbindungen')
  expect(tabAus('quatsch')).toBeNull()
  expect(tabAus(null)).toBeNull()
})

it('Tab-Namen sind übersetzt', async () => {
  const { TABS } = await import('./sections')
  const dict = en as Record<string, string>
  const missing = TABS.flatMap((x) => [x.title, navLabel(x.title)]).filter((k) => !(k in dict))
  expect(missing).toEqual([])
})
