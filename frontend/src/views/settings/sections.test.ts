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
