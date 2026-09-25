import { useSyncExternalStore } from 'react'
import { ApiError } from './api'

// Vorlesen über Gemini TTS (/api/tts liefert WAV). Es spielt immer nur EINE
// Wiedergabe: ein neuer Start stoppt die alte. "owner" kennzeichnet, wer
// gerade spielt (z. B. die Nachrichten-ID im Chat), damit genau dieser Knopf
// ⏳/⏹ zeigt.

export interface TtsOptions {
  /** Überschreibt die gespeicherte Stimme (Hörprobe in den Einstellungen). */
  voice?: string
  model?: string
  style?: string
}

export interface SayState {
  owner: string | null
  phase: 'idle' | 'loading' | 'playing'
}

let state: SayState = { owner: null, phase: 'idle' }
let audio: HTMLAudioElement | null = null
let url: string | null = null
// Zählt Starts: eine späte Antwort eines überholten Aufrufs erkennt sich daran.
let gen = 0
const listeners = new Set<() => void>()

function set(next: SayState) {
  state = next
  listeners.forEach((l) => l())
}

function release() {
  if (audio) audio.pause()
  if (url) URL.revokeObjectURL(url)
  audio = null
  url = null
}

/** Laufende Wiedergabe (oder deren Laden) abbrechen. */
export function stopSay() {
  release()
  set({ owner: null, phase: 'idle' })
}

/**
 * Text vorlesen. Löst auf, sobald die Wiedergabe läuft; wirft bei Fehlern
 * (Meldung des Servers, z. B. fehlender Gemini-Key).
 */
export async function say(text: string, opts: TtsOptions & { owner?: string } = {}) {
  const { owner = '', ...tts } = opts
  stopSay()
  if (!text) return
  const mine = ++gen
  set({ owner, phase: 'loading' })
  try {
    const r = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, ...tts }),
    })
    if (!r.ok) {
      let m = 'Vorlesen fehlgeschlagen'
      try {
        m = ((await r.json()) as { error?: string }).error || m
      } catch {
        /* keine JSON-Antwort */
      }
      throw new ApiError(m, r.status)
    }
    const blob = await r.blob()
    // Inzwischen etwas anderes gestartet oder gestoppt? Dann verwerfen.
    if (gen !== mine || state.phase !== 'loading') return
    url = URL.createObjectURL(blob)
    audio = new Audio(url)
    audio.onended = stopSay
    set({ owner, phase: 'playing' })
    await audio.play()
  } catch (e) {
    if (gen === mine) stopSay()
    throw e
  }
}

const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => {
    listeners.delete(l)
  }
}

/** Aktueller Wiedergabe-Zustand für Knöpfe (🔊/⏳/⏹). */
export function useSayState(): SayState {
  return useSyncExternalStore(subscribe, () => state)
}
