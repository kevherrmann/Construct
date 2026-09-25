import { create } from 'zustand'

// Vorlesen über Gemini TTS (/api/tts). Immer nur eine Wiedergabe gleichzeitig;
// `owner` ist die Kennung dessen, der gerade spricht (z. B. eine Nachricht),
// damit genau dessen 🔊-Knopf ⏳/⏹ zeigt.

interface SayStore {
  owner: string | null
  state: 'idle' | 'loading' | 'playing'
  error: { owner: string; message: string } | null
  play: (owner: string, text: string, opts?: Record<string, string>) => Promise<void>
  stop: () => void
}

let audio: HTMLAudioElement | null = null

function release() {
  if (!audio) return
  audio.pause()
  URL.revokeObjectURL(audio.src)
  audio = null
}

export const useSay = create<SayStore>((set, get) => ({
  owner: null,
  state: 'idle',
  error: null,
  stop() {
    release()
    set({ owner: null, state: 'idle' })
  },
  async play(owner, text, opts) {
    get().stop()
    if (!text.trim()) return
    set({ owner, state: 'loading', error: null })
    try {
      const r = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, ...opts }),
      })
      if (!r.ok) {
        let msg = 'Vorlesen fehlgeschlagen'
        try {
          msg = ((await r.json()) as { error?: string }).error ?? msg
        } catch {
          /* kein JSON */
        }
        throw new Error(msg)
      }
      const url = URL.createObjectURL(await r.blob())
      // Inzwischen etwas anderes gestartet oder gestoppt?
      if (get().owner !== owner) {
        URL.revokeObjectURL(url)
        return
      }
      audio = new Audio(url)
      audio.onended = () => get().stop()
      set({ state: 'playing' })
      await audio.play()
    } catch (e) {
      release()
      set({ owner: null, state: 'idle', error: { owner, message: (e as Error).message } })
      setTimeout(() => {
        if (get().error?.owner === owner) set({ error: null })
      }, 3000)
      throw e
    }
  },
}))

/** Vorlesbarer Text: Markdown genügt, der Server entfernt Code und Formatierung. */
export function speakableText(blocks: { t: string; text?: string }[]): string {
  return blocks
    .filter((b) => b.t === 'text' && b.text)
    .map((b) => b.text)
    .join('\n')
    .trim()
}
