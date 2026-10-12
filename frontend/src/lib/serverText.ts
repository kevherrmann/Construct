import i18n from 'i18next'
import en from '@/i18n/en.json'

// Texte, die fertig vom Server kommen (Anbieter-Hinweise, Fehlermeldungen,
// Modellbeschreibungen), schreibt das Backend auf Deutsch. Die alte Oberfläche
// hat sie im DOM übersetzt; hier geschieht das gezielt an den Stellen, die sie
// anzeigen. Unbekanntes bleibt, wie es ist — lieber Deutsch als gar nichts.

// Texte mit eingesetzten Werten.
const RX: [RegExp, string][] = [
  [/^Ordner (.+) nicht lesbar$/, 'Folder $1 unreadable'],
  // Lokale Stimme (server/tts_lokal.py)
  [
    /^Zu wenig freier Grafikspeicher für die lokale Stimme: ([\d.]+) GB frei, gebraucht werden etwa (\d+) GB\. Läuft gerade ein Spiel oder ein anderes KI-Modell\?$/,
    'Not enough free graphics memory for the local voice: $1 GB free, about $2 GB needed. Is a game or another AI model running?',
  ],
  [
    /^Die lokale Stimme ist beim Start abgebrochen — meist zu wenig freier Grafikspeicher\. Details: (.+)$/,
    'The local voice stopped while starting — usually not enough free graphics memory. Details: $1',
  ],
  [
    /^Die lokale Stimme antwortet nach (\d+)s nicht\.$/,
    'The local voice is not responding after $1 s.',
  ],
  [/^Die lokale Stimme ließ sich nicht starten: (.+)$/, 'The local voice could not be started: $1'],
  [/^Lokale Stimme nicht erreichbar: (.+)$/, 'Local voice not reachable: $1'],
  [/^(\S+) beendet mit Code (-?\d+)$/, '$1 exited with code $2'],
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
