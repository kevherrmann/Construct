import { useSyncExternalStore } from 'react'
import { ApiError } from './api'

// Vorlesen über /api/tts (liefert WAV). Es spielt immer nur EINE
// Wiedergabe: ein neuer Start stoppt die alte. "owner" kennzeichnet, wer
// gerade spielt (z. B. die Nachrichten-ID im Chat), damit genau dieser Knopf
// ⏳/⏹ zeigt.
//
// Die lokale Stimme liefert den Text in Stücken (Kopfzeile X-TTS-Teile): das
// erste spielt, sobald es da ist, das nächste wird schon geholt, während das
// vorige läuft. Gemini liefert alles in einem Stück.

export interface TtsOptions {
  /** Überschreibt die gespeicherte Stimme (Hörprobe in den Einstellungen). */
  voice?: string
  model?: string
  style?: string
  /** Gemini erzwingen, auch wenn die lokale Stimme eingeschaltet ist. */
  engine?: 'gemini'
}

export interface SayState {
  owner: string | null
  phase: 'idle' | 'loading' | 'playing'
  /** Letzter Fehler, 10 s lang — so zeigt auch automatisches Vorlesen ⚠ am Knopf. */
  error: { owner: string; message: string } | null
}

let state: SayState = { owner: null, phase: 'idle', error: null }
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
  set({ owner: null, phase: 'idle', error: state.error })
}

function fehler(owner: string, e: unknown) {
  stopSay()
  const err = { owner, message: (e as Error).message }
  set({ ...state, error: err })
  setTimeout(() => {
    if (state.error === err) set({ ...state, error: null })
  }, 10000)
}

async function holen(text: string, tts: TtsOptions, teil: number) {
  const r = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, ...tts, teil }),
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
  return { blob: await r.blob(), teile: Number(r.headers.get('X-TTS-Teile')) || 1 }
}

/**
 * Text vorlesen. Löst auf, sobald die Wiedergabe läuft; wirft bei Fehlern
 * (Meldung des Servers, z. B. fehlender Gemini-Key). Scheitert ein späteres
 * Stück, zeigt der Knopf ⚠ — geworfen wird dann nicht mehr.
 */
export async function say(text: string, opts: TtsOptions & { owner?: string } = {}) {
  const { owner = '', ...tts } = opts
  stopSay()
  if (!text) return
  const mine = ++gen
  // Noch dieselbe Wiedergabe? (Nicht überholt und nicht gestoppt.)
  const lebt = () => gen === mine && state.phase !== 'idle'
  set({ owner, phase: 'loading', error: null })

  let teile = 1
  const vorrat = new Map<number, Promise<Blob>>()
  const hole = (i: number) => {
    let p = vorrat.get(i)
    if (!p) {
      p = holen(text, tts, i).then((r) => r.blob)
      p.catch(() => undefined) // Fehler zeigt erst, wer darauf wartet
      vorrat.set(i, p)
    }
    return p
  }
  const spiele = (blob: Blob, i: number) => {
    release()
    url = URL.createObjectURL(blob)
    audio = new Audio(url)
    audio.onended = () => void weiter(i + 1)
    set({ owner, phase: 'playing', error: null })
    return audio.play()
  }
  const weiter = async (i: number) => {
    if (!lebt()) return
    if (i >= teile) return stopSay()
    if (i + 1 < teile) void hole(i + 1)
    try {
      const blob = await hole(i)
      if (lebt()) await spiele(blob, i)
    } catch (e) {
      if (lebt()) fehler(owner, e)
    }
  }

  try {
    const erst = await holen(text, tts, 0)
    // Inzwischen etwas anderes gestartet oder gestoppt? Dann verwerfen.
    if (!lebt()) return
    teile = erst.teile
    if (teile > 1) void hole(1)
    await spiele(erst.blob, 0)
  } catch (e) {
    if (gen === mine) fehler(owner, e)
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
