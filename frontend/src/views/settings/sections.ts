// Abschnitte der Einstellungsseite, in Anzeigereihenfolge. Seite UND
// Navigation links lesen diese eine Liste — in der alten Oberfläche wurde die
// Navigation aus den Überschriften gebaut, weil eine zweite, feste Liste
// auseinanderlief, sobald ein Abschnitt dazukam.
export const SECTIONS = [
  { id: 'team', title: '🏢 TEAM' },
  { id: 'sprache', title: '🌐 SPRACHE' },
  { id: 'kacheln', title: '⚙ KACHELN' },
  { id: 'modelle', title: '🧠 MODELLE & ANBIETER' },
  { id: 'mail', title: '📧 E-MAIL-KONTEN' },
  { id: 'vorlesen', title: '🔊 VORLESEN' },
  // nav: wo navLabel falsch großschreibt (deutsch nur Hauptwörter groß)
  { id: 'bilder', title: '🖌 BILDER ERZEUGEN', nav: 'Bilder erzeugen' },
  { id: 'telegram', title: '✈ TELEGRAM' },
  { id: 'updates', title: '🔄 AKTUALISIERUNG' },
  { id: 'namen', title: '🙋 NAMEN' },
  { id: 'charakter', title: '📜 CHARAKTER' },
  { id: 'farbwelt', title: '🎨 FARBWELT' },
  { id: 'hintergrund', title: '🖼 HINTERGRUND' },
  { id: 'klang', title: '🎵 SOUNDS & MUSIK' },
  { id: 'beenden', title: '⏻ BEENDEN' },
] as const

export type SectionId = (typeof SECTIONS)[number]['id']

export const sectionDomId = (id: SectionId) => `set-${id}`

// Tabs: links wählt man einen Bereich, rechts steht nur der — statt einer
// langen Liste, durch die man scrollt. Jeder Abschnitt gehört genau einem Tab.
export const TABS = [
  { id: 'allgemein', title: '⚙ ALLGEMEIN', sections: ['team', 'sprache', 'kacheln', 'namen'] },
  { id: 'modelle', title: '🧠 MODELLE', sections: ['modelle', 'bilder'] },
  { id: 'assistent', title: '📜 ASSISTENT', sections: ['charakter', 'vorlesen'] },
  { id: 'verbindungen', title: '🔌 VERBINDUNGEN', sections: ['mail', 'telegram'] },
  { id: 'aussehen', title: '🎨 AUSSEHEN', sections: ['farbwelt', 'hintergrund', 'klang'] },
  { id: 'system', title: '🖥 SYSTEM', sections: ['updates', 'beenden'] },
] as const satisfies readonly { id: string; title: string; sections: readonly SectionId[] }[]

export type TabId = (typeof TABS)[number]['id']

/** Tab aus der Adresse (?tab=…): ein Tab-Name oder ein Abschnitt (dessen Tab). */
export function tabAus(wert: string | null): TabId | null {
  if (!wert) return null
  const tab = TABS.find((x) => x.id === wert || (x.sections as readonly string[]).includes(wert))
  return tab?.id ?? null
}

/** „🧠 MODELLE & ANBIETER“ → „Modelle & Anbieter“ (deutscher Schlüssel fürs Menü). */
export const navLabel = (title: string) =>
  title
    .replace(/^[^\p{L}]+/u, '')
    .trim()
    .toLowerCase()
    .replace(/(^|[\s-])\p{L}/gu, (m) => m.toUpperCase())

/** Menüname eines Abschnitts (deutscher Schlüssel): eigener, sonst aus der Überschrift. */
export const abschnittName = (x: (typeof SECTIONS)[number]) =>
  'nav' in x ? x.nav : navLabel(x.title)
