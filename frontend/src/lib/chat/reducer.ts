import { tk } from '@/lib/i18n'
import { produce } from 'immer'
import type { Block, BotItem, ChatItem, StreamEvent } from './types'

// Baut aus den Stream-Events eines Laufs die Anzeige. Rein funktional: bei
// einem Reconnect spielt der Server den ganzen Lauf noch einmal ab, und die
// Anzeige entsteht einfach neu aus initialRun().

export interface RunState {
  /** Sprechblasen dieses Laufs — mehrere, wenn Nachrichten eingeworfen wurden. */
  items: ChatItem[]
  /** Write/Edit-Aufrufe dieses Zuges: tool-id → Pfad, ok = erfolgreich. */
  written: Record<string, { path: string; ok: boolean }>
}

let seq = 0
export const newId = (p = 'i') => `${p}${++seq}-${Date.now().toString(36)}`

const botTurn = (): BotItem => ({ kind: 'bot', id: newId('b'), blocks: [], thinking: true })

export const initialRun = (): RunState => ({ items: [botTurn()], written: {} })

function currentTurn(s: RunState): BotItem {
  const last = s.items[s.items.length - 1]
  if (last?.kind === 'bot') return last
  const t = botTurn()
  s.items.push(t)
  return t
}

/** Offenen Text-Block abschließen (Caret weg, Pfade werden verlinkt). */
function endText(turn: BotItem) {
  const last = turn.blocks[turn.blocks.length - 1]
  if (last?.t === 'text') last.streaming = false
}

const WRITE_TOOL = /^(Write|Edit|MultiEdit|NotebookEdit|write|edit)/i

export function toolPath(input: unknown): string {
  if (!input || typeof input !== 'object') return ''
  const i = input as Record<string, unknown>
  return String(i.file_path ?? i.path ?? i.notebook_path ?? '')
}

export function skillUseLabel(input: unknown): string {
  if (!input || typeof input !== 'object') return ''
  const i = input as Record<string, unknown>
  return String(i.command ?? i.name ?? i.skill ?? Object.values(i)[0] ?? '').slice(0, 70)
}

export function skillFileName(p: string): string {
  const m = /skills\/([^/]+)\/SKILL\.md$/i.exec(p)
  return m ? m[1]! : (p.split('/').filter(Boolean).pop() ?? '')
}

export const applyEvent = (state: RunState, ev: StreamEvent): RunState =>
  produce(state, (s) => {
    switch (ev.type) {
      case 'text': {
        const turn = currentTurn(s)
        turn.thinking = false
        const last = turn.blocks[turn.blocks.length - 1]
        if (last?.t === 'text' && last.streaming) last.text += ev.text
        else turn.blocks.push({ t: 'text', text: ev.text, streaming: true })
        break
      }
      case 'user_inject': {
        const turn = currentTurn(s)
        endText(turn)
        turn.thinking = false
        s.items.push({
          kind: 'user',
          id: newId('u'),
          text: ev.text ?? '',
          urls: ev.urls ?? [],
          editable: false,
        })
        s.items.push(botTurn())
        break
      }
      case 'thinking_marker': {
        const turn = currentTurn(s)
        turn.thinking = false
        if (!turn.blocks.some((b) => b.t === 'thinkmark')) turn.blocks.unshift({ t: 'thinkmark' })
        break
      }
      case 'tool': {
        const turn = currentTurn(s)
        turn.thinking = false
        endText(turn)
        const input = ev.input ?? {}
        const fp = toolPath(input)
        if (/^skill$/i.test(ev.name)) {
          turn.blocks.push({ t: 'skill', kind: 'used', label: skillUseLabel(input) })
        } else {
          if (/SKILL\.md$/i.test(fp))
            turn.blocks.push({ t: 'skill', kind: 'saved', label: skillFileName(fp) })
          turn.blocks.push({ t: 'tool', id: ev.id, name: ev.name, input })
        }
        // Ergebnisdateien: am Zugende als Zeile mit Links — man muss nicht im
        // Verlauf nach dem Pfad suchen. SKILL.md hat schon ihr Banner.
        if (ev.id && fp && WRITE_TOOL.test(ev.name) && !/SKILL\.md$/i.test(fp))
          s.written[ev.id] = { path: fp, ok: false }
        break
      }
      case 'tool_result': {
        for (const item of s.items) {
          if (item.kind !== 'bot') continue
          const b = item.blocks.find(
            (x): x is Extract<Block, { t: 'tool' }> => x.t === 'tool' && !!ev.id && x.id === ev.id,
          )
          if (b) b.result = { content: ev.content ?? '', isError: !!ev.is_error }
        }
        if (ev.id && s.written[ev.id]) s.written[ev.id]!.ok = !ev.is_error
        break
      }
      case 'stats': {
        const turn = currentTurn(s)
        turn.thinking = false
        endText(turn)
        turn.blocks.push({
          t: 'stats',
          durationMs: ev.duration_ms,
          out: ev.out,
          ctx: ev.ctx,
          model: ev.model,
        })
        const paths = [
          ...new Set(
            Object.values(s.written)
              .filter((w) => w.ok)
              .map((w) => w.path),
          ),
        ]
        s.written = {}
        if (paths.length) turn.blocks.push({ t: 'files', paths })
        break
      }
      case 'nachlauf': {
        // Zug fertig, aber claude wartet noch auf eigene Hintergrundaufgaben.
        // Der Prozess bleibt offen; was der Hintergrund liefert, kommt als
        // neue Sprechblase (neuer_zug).
        const turn = currentTurn(s)
        turn.thinking = false
        endText(turn)
        turn.blocks.push({
          t: 'note',
          note: {
            key: tk(
              '⏳ läuft noch im Hintergrund: {tasks} — ich melde mich, sobald es fertig ist.',
            ),
            params: { tasks: (ev.tasks ?? []).join(' · ') },
          },
        })
        break
      }
      case 'neuer_zug': {
        const turn = currentTurn(s)
        endText(turn)
        turn.thinking = false
        s.items.push(botTurn())
        break
      }
      case 'done': {
        const turn = currentTurn(s)
        turn.thinking = false
        endText(turn)
        break
      }
      case 'error': {
        const turn = currentTurn(s)
        turn.thinking = false
        endText(turn)
        turn.blocks.push({ t: 'error', message: ev.message })
        break
      }
      default:
        break
    }
  })

/** Hinweis an den laufenden Zug hängen (Reconnect, Gestoppt, …). */
export const addRunNote = (state: RunState, note: Block & { t: 'note' }): RunState =>
  produce(state, (s) => {
    const turn = currentTurn(s)
    turn.thinking = false
    endText(turn)
    turn.blocks.push(note)
  })
