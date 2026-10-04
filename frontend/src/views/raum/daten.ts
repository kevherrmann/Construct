import { useMemo } from 'react'
import { useWerkstatt } from '@/api/chat'
import type { Block, ChatItem } from '@/lib/chat/types'
import { useChat } from '@/stores/chat'

// Gesprächsdaten, die mehrere Teile des Raums brauchen (Karten, Fernseher).

/** Werkzeuge, die im Terminal laufen. */
export const IST_BEFEHL = /^(Bash|BashOutput|terminal|execute_code)\b/

export function useItems(): ChatItem[] {
  const conv = useChat((st) => st.active())
  return useMemo(() => (conv ? [...conv.history, ...(conv.run?.items ?? [])] : []), [conv])
}

export function toolBlocks(items: ChatItem[]) {
  return items.flatMap((it) =>
    it.kind === 'bot'
      ? it.blocks.filter((b): b is Extract<Block, { t: 'tool' }> => b.t === 'tool')
      : [],
  )
}

/** Werkstatt-Daten der aktiven Session (Dateien, Befehle, git) vom Server. */
export function useWerkstattDaten() {
  const sid = useChat((st) => st.active()?.sessionId)
  const busy = useChat((st) => !!st.active()?.busy)
  const stand = useChat((st) => st.active()?.history.length ?? 0)
  return useWerkstatt(sid, busy, stand).data
}

export interface Befehl {
  command: string
  description: string
  output: string | null
  isError: boolean
}

/** Befehle aus Verlauf + laufendem Teil, wie der Chat sie live kennt. */
export function befehleAus(items: ChatItem[]): Befehl[] {
  return toolBlocks(items)
    .filter((b) => IST_BEFEHL.test(b.name))
    .map((b) => {
      const inp = (b.input ?? {}) as { command?: string; description?: string }
      return {
        command: inp.command ?? b.name,
        description: inp.description ?? '',
        output: b.result ? b.result.content : null,
        isError: !!b.result?.isError,
      }
    })
}

/** Viele Dateien im selben Ordner (z.B. gebaute Assets) zu einer Zeile. */
export function gruppiert<T extends { path: string }>(
  liste: T[],
  max = 6,
): ({ art: 'datei'; d: T } | { art: 'ordner'; ordner: string; n: number })[] {
  const ordner = (p: string) => p.slice(0, p.lastIndexOf('/'))
  const zahl = new Map<string, number>()
  for (const d of liste) zahl.set(ordner(d.path), (zahl.get(ordner(d.path)) ?? 0) + 1)
  const gesehen = new Set<string>()
  const out: ({ art: 'datei'; d: T } | { art: 'ordner'; ordner: string; n: number })[] = []
  for (const d of liste) {
    const o = ordner(d.path)
    const n = zahl.get(o) ?? 0
    if (n <= max) out.push({ art: 'datei', d })
    else if (!gesehen.has(o)) {
      gesehen.add(o)
      out.push({ art: 'ordner', ordner: o, n })
    }
  }
  return out
}
