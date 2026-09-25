import type { ThemeName } from './bootstrap'

export interface ThemeInfo {
  key: ThemeName
  name: string
  description: string
  /** Vorschau-Punkte in der Auswahl: Hintergrund, Akzent, gedämpft. */
  swatch: [string, string, string]
  light?: boolean
}

// Die echten Farben stehen in styles/themes.css; die Vorschau hier doppelt zu
// halten erspart DOM-Messungen pro Theme.
export const THEMES: ThemeInfo[] = [
  {
    key: 'matrix',
    name: 'Matrix',
    description: 'Grün auf Schwarz. Der Ursprung.',
    swatch: ['#000600', '#00ff41', '#0d3d18'],
  },
  {
    key: 'bernstein',
    name: 'Bernstein',
    description: 'Alter Bernstein-Monitor — warm, augenschonend.',
    swatch: ['#0a0600', '#ffb648', '#4a2f0a'],
  },
  {
    key: 'eis',
    name: 'Eis',
    description: 'Kühles Cyan auf Tiefblau.',
    swatch: ['#00060c', '#5fd8ff', '#0d3446'],
  },
  {
    key: 'space',
    name: 'Space',
    description: 'Violett auf Nachtblau.',
    swatch: ['#06030f', '#b98bff', '#2c1a4d'],
  },
  {
    key: 'asche',
    name: 'Asche',
    description: 'Neutrales Grau — zurückhaltend, gut zum Lesen.',
    swatch: ['#0c0e11', '#d8dee4', '#2b3138'],
  },
  {
    key: 'blut',
    name: 'Blut',
    description: 'Rot auf Schwarz. Laut.',
    swatch: ['#0b0303', '#ff5f57', '#481815'],
  },
  {
    key: 'papier',
    name: 'Papier',
    description: 'Hell: Waldgrün auf warmem Papierweiß.',
    swatch: ['#f5f2ea', '#1d6b45', '#d3dfd6'],
    light: true,
  },
  {
    key: 'nebel',
    name: 'Nebel',
    description: 'Hell: Tintenblau auf kühlem Grau.',
    swatch: ['#eef1f6', '#2757b8', '#d5dce8'],
    light: true,
  },
]

export function applyTheme(theme: ThemeName) {
  const root = document.documentElement
  if (theme === 'matrix') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}

/** Plasma an/aus: steuert die Glas-Regeln im CSS (html[data-plasma]). */
export function applyPlasma(on: boolean) {
  const root = document.documentElement
  if (on) root.setAttribute('data-plasma', '')
  else root.removeAttribute('data-plasma')
}
