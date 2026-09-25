// Schriften, die CONSTRUCT mitbringt — Google Fonts (OFL), aber über npm
// gebündelt statt zur Laufzeit von Google geladen: CONSTRUCT bleibt offline-
// fähig und fragt keinen Dritten. Der Browser lädt nur die gewählte Schrift.
// Schlüssel wie config.FONTS im Backend.

export interface FontInfo {
  key: string
  name: string
  family: string
  /** Deutscher Quelltext. */
  description: string
}

export const FONTS: FontInfo[] = [
  {
    key: 'share-tech-mono',
    name: 'Share Tech Mono',
    family: "'Share Tech Mono', monospace",
    description: 'Die Terminal-Schrift von CONSTRUCT.',
  },
  {
    key: 'jetbrains-mono',
    name: 'JetBrains Mono',
    family: "'JetBrains Mono Variable', monospace",
    description: 'Moderne Programmierer-Schrift, sehr gut lesbar.',
  },
  {
    key: 'ibm-plex-mono',
    name: 'IBM Plex Mono',
    family: "'IBM Plex Mono', monospace",
    description: 'Technisch-nüchtern, etwas wärmer.',
  },
  {
    key: 'space-grotesk',
    name: 'Space Grotesk',
    family: "'Space Grotesk Variable', sans-serif",
    description: 'Futuristische Grotesk mit Charakter.',
  },
  {
    key: 'exo-2',
    name: 'Exo 2',
    family: "'Exo 2 Variable', sans-serif",
    description: 'Sci-Fi — passt zum Construct.',
  },
  {
    key: 'inter',
    name: 'Inter',
    family: "'Inter Variable', system-ui, sans-serif",
    description: 'Klar und neutral.',
  },
]

/** Gewählte Schrift setzen; "" = automatisch (die Vorgabe des Themes bzw. von Plasma). */
export function applyFont(key: string) {
  const f = FONTS.find((x) => x.key === key)
  const root = document.documentElement.style
  if (f) root.setProperty('--font', f.family)
  else root.removeProperty('--font')
}
