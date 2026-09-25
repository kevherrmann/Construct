import type { Provider } from '@/api/providers'

// Modell-Auswahl: Claude (voll integriert, mit Tools) + externe Anbieter über
// Hermes. Externe Werte heißen "anbieter:modell", z. B. "openai:gpt-4o" oder
// "ollama:gemma3:12b".
//
// Volle Modell-IDs statt Aliase ('sonnet', 'fable'): ein Alias zeigt immer auf
// das jeweils neueste Modell seiner Reihe, und man sieht ihm nicht an, welches
// das gerade IST. Nachmessen, wenn ein neues Modell erscheint:
//   claude -p "ok" --model <name> --output-format json | jq .modelUsage
// Gemessen am 04.09.2026 mit Claude Code 2.1.280: fable→claude-fable-5-1,
// opus→claude-opus-5-5, sonnet→claude-sonnet-5, haiku→claude-haiku-4-5-20251001.

export interface ModelInfo {
  v: string
  l: string
  d: string
  prov?: string
}

export const CLAUDE_MODELS: ModelInfo[] = [
  { v: '', l: 'Standard', d: 'Konto-Standard von Claude Code' },
  {
    v: 'claude-opus-5-5',
    l: 'Opus 5.5',
    d: 'neuestes Opus — stark für Coding und komplexe Aufgaben',
  },
  {
    v: 'claude-fable-5-1',
    l: 'Fable 5.1',
    d: 'stärkstes Modell — für die härtesten und längsten Aufgaben',
  },
  { v: 'claude-opus-5', l: 'Opus 5', d: 'Vorgänger von Opus 5.5' },
  { v: 'claude-sonnet-5', l: 'Sonnet 5', d: 'schnell, schont das Limit' },
  { v: 'claude-haiku-4-5', l: 'Haiku 4.5', d: 'am schnellsten — kleine Aufgaben' },
]

/** Vorgabe für alle neuen Gespräche, solange nie etwas gewählt wurde. */
export const DEFAULT_MODEL = 'claude-opus-5-5'

const MODEL_ALIAS: Record<string, string> = {
  fable: 'claude-fable-5-1',
  opus: 'claude-opus-5-5',
  sonnet: 'claude-sonnet-5',
  haiku: 'claude-haiku-4-5',
}

export const PROV_ICON: Record<string, string> = {
  openai: '🟢',
  gemini: '✦',
  deepseek: '🐋',
  ollama: '🦙',
  bonsai: '🌱',
}
export const provIcon = (id?: string) => (id ? (PROV_ICON[id] ?? '🌐') : '')

export function extModels(providers: Provider[]): (ModelInfo & { cap: boolean | null })[] {
  return providers
    .filter((p) => p.configured)
    .flatMap((p) =>
      (p.models ?? []).map((m) => ({
        v: `${p.id}:${m}`,
        l: m,
        d: p.label,
        prov: p.id,
        // true = sicher werkzeugfähig, null/undefined = unbekannt
        cap: p.tools?.[m] ?? null,
      })),
    )
}

/**
 * Anzeige-Info zu einem Modellwert. Alte Auswahl aus dem localStorage und
 * Rückmeldungen aus Transkripten kommen als Alias oder mit Zusätzen an
 * (`claude-haiku-4-5-20251001`, `…[1m]`). Ohne diese Zuordnung fiele der
 * Picker bei jeder solchen Angabe stumm auf "Standard" zurück — und zeigte
 * damit genau das Falsche an.
 */
export function modelInfo(v: string, providers: Provider[] = []): ModelInfo | null {
  const c = CLAUDE_MODELS.find((x) => x.v === v)
  if (c) return c
  const e = extModels(providers).find((x) => x.v === v)
  if (e) return e
  if (v && !v.includes(':')) {
    const raw = v.replace(/\[.*\]$/, '')
    // Längster passender Präfix gewinnt, sonst bliebe "claude-opus-5-5[1m]"
    // bei "claude-opus-5" hängen.
    const hit =
      MODEL_ALIAS[raw] ??
      CLAUDE_MODELS.slice(1)
        .filter((x) => raw.startsWith(x.v))
        .sort((a, b) => b.v.length - a.v.length)[0]?.v
    if (hit) return CLAUDE_MODELS.find((x) => x.v === hit) ?? null
    // Claude-Modell, das nicht (mehr) zur Auswahl steht: mit roher ID zeigen —
    // "Standard" wäre hier schlicht gelogen.
    if (raw.startsWith('claude-'))
      return { v, l: raw.replace(/^claude-/, ''), d: 'nicht mehr in der Auswahl' }
  }
  // Unbekannt, aber extern (Anbieterliste evtl. noch nicht geladen) → trotzdem zeigen.
  if (v.includes(':')) {
    const [prov, ...rest] = v.split(':')
    return { v, l: rest.join(':'), d: prov!, prov }
  }
  return null
}

export const MODES = [
  { v: 'bypassPermissions', l: '⚡ Auto', d: 'volle Rechte — alles läuft automatisch' },
  { v: 'plan', l: '📋 Plan', d: 'nur lesen / planen, ändert nichts' },
  { v: 'default', l: '🛡 Standard', d: 'fragt nach (im Web eingeschränkt)' },
] as const
export type Mode = (typeof MODES)[number]['v']
