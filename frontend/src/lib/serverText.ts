import i18n from 'i18next'

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
]

function line(s: string): string {
  const n = s.trim()
  if (!n) return s
  if (i18n.exists(n)) return i18n.t(n)
  for (const [re, en] of RX) if (re.test(n)) return n.replace(re, en)
  // Anbieternamen wie "Ollama (lokal)".
  return s.replace(/\((lokal|LOKAL)\)/g, (_, w: string) => (w === 'LOKAL' ? '(LOCAL)' : '(local)'))
}

/** Servertext in die Oberflächensprache bringen, zeilenweise. */
export function trServer(s: string | null | undefined): string {
  if (!s) return ''
  if (i18n.language !== 'en') return s
  return s.split('\n').map(line).join('\n')
}
