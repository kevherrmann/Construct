import i18n from 'i18next'
import en from '@/i18n/en.json'

// Texte, die fertig vom Server kommen (Anbieter-Hinweise, Fehlermeldungen,
// Modellbeschreibungen), schreibt das Backend auf Deutsch. Die alte Oberfläche
// hat sie im DOM übersetzt; hier geschieht das gezielt an den Stellen, die sie
// anzeigen. Unbekanntes bleibt, wie es ist — lieber Deutsch als gar nichts.

// Texte mit eingesetzten Werten.
const RX: [RegExp, string][] = [
  [
    /^PrismML-Bonsai über den llama-server des Bonsai-Demos — startet erst beim ersten Prompt und räumt den VRAM nach (\d+) Min Leerlauf wieder frei$/,
    "PrismML Bonsai via the Bonsai demo's llama-server — starts on the first prompt and frees the VRAM after $1 min of inactivity",
  ],
  [/^Ordner (.+) nicht lesbar$/, 'Folder $1 unreadable'],
  [/^Ordner (.+) nicht wählbar$/, 'Folder $1 not selectable'],
]

// Satzteile mit eingesetzten Werten ("Unbekannter Anbieter für x@y — …"):
// bekannte mehrwortige Stücke werden einzeln ersetzt, längste zuerst — wie
// in der alten Oberfläche. Einzelne Wörter bewusst nicht, sonst würden
// Namen und Adressen mit übersetzt.
let frag: RegExp | null = null
function fragments(): RegExp {
  if (frag) return frag
  const keys = Object.keys(en)
    .filter((k) => k.includes(' ') && k.length > 8)
    .sort((a, b) => b.length - a.length)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  frag = new RegExp(keys.join('|'), 'g')
  return frag
}

function line(s: string): string {
  const n = s.trim()
  if (!n) return s
  if (i18n.exists(n)) return i18n.t(n)
  for (const [re, to] of RX) if (re.test(n)) return n.replace(re, to)
  const dict = en as Record<string, string>
  s = s.replace(fragments(), (m) => dict[m] ?? m)
  // Anbieternamen wie "Ollama (lokal)".
  return s.replace(/\((lokal|LOKAL)\)/g, (_, w: string) => (w === 'LOKAL' ? '(LOCAL)' : '(local)'))
}

/** Servertext in die Oberflächensprache bringen, zeilenweise. */
export function trServer(s: string | null | undefined): string {
  if (!s) return ''
  if (i18n.language !== 'en') return s
  return s.split('\n').map(line).join('\n')
}
