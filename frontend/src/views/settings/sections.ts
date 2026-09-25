// Abschnitte der Einstellungsseite, in Anzeigereihenfolge. Seite UND
// Navigation links lesen diese eine Liste — in der alten Oberfläche wurde die
// Navigation aus den Überschriften gebaut, weil eine zweite, feste Liste
// auseinanderlief, sobald ein Abschnitt dazukam.
export const SECTIONS = [
  { id: 'sprache', title: '🌐 SPRACHE' },
  { id: 'kacheln', title: '⚙ KACHELN' },
  { id: 'modelle', title: '🧠 MODELLE & ANBIETER' },
  { id: 'mail', title: '📧 E-MAIL-KONTEN' },
  { id: 'vorlesen', title: '🔊 VORLESEN' },
  { id: 'telegram', title: '✈ TELEGRAM' },
  { id: 'updates', title: '🔄 AKTUALISIERUNG' },
  { id: 'namen', title: '🙋 NAMEN' },
  { id: 'charakter', title: '📜 CHARAKTER' },
  { id: 'farbwelt', title: '🎨 FARBWELT' },
  { id: 'hintergrund', title: '🖼 HINTERGRUND' },
] as const

export type SectionId = (typeof SECTIONS)[number]['id']

export const sectionDomId = (id: SectionId) => `set-${id}`

/** „🧠 MODELLE & ANBIETER“ → „Modelle & Anbieter“ (deutscher Schlüssel fürs Menü). */
export const navLabel = (title: string) =>
  title
    .replace(/^[^\p{L}]+/u, '')
    .trim()
    .toLowerCase()
    .replace(/(^|[\s-])\p{L}/gu, (m) => m.toUpperCase())
