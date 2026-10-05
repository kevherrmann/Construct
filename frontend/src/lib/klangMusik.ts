// Noten für die Coding-Musik im Raum: ruhiger Lo-Fi-Beat mit Rhodes-artigen
// Akkorden. Hier steht nur, WAS wann spielt — als reine Daten, damit es sich
// testen lässt. Wie es klingt, macht klang.ts.

export const BPM = 72
export const SCHLAG = 60 / BPM
export const TAKT = 4 * SCHLAG
/** Achtel-Swing: die zweite Achtel kommt so viel später (Anteil eines Schlags). */
const SWING = 0.09

export type Stimme = 'akkord' | 'bass' | 'melodie' | 'kick' | 'snare' | 'hihat'

export interface Ereignis {
  stimme: Stimme
  /** Beginn in Sekunden ab Taktanfang. */
  t: number
  /** MIDI-Note (Instrumente) — Schlagzeug hat keine. */
  note?: number
  /** Länge in Sekunden. */
  dauer: number
  /** Anschlagstärke 0–1. */
  vel: number
}

interface Akkord {
  bass: number
  toene: number[]
}

// Fmaj9 – Em7 – Dm9 – Cmaj7, eng gesetzt in der Mittellage. Danach dieselbe
// Folge mit Am9 statt Cmaj7, damit acht Takte nicht wie vier klingen.
const FOLGE: Akkord[] = [
  { bass: 41, toene: [57, 60, 64, 67] },
  { bass: 40, toene: [55, 59, 62, 66] },
  { bass: 38, toene: [53, 57, 60, 64] },
  { bass: 36, toene: [55, 59, 60, 64] },
  { bass: 41, toene: [57, 60, 64, 67] },
  { bass: 40, toene: [55, 59, 62, 67] },
  { bass: 38, toene: [53, 57, 60, 65] },
  { bass: 45, toene: [55, 59, 60, 64] },
]

/** C-Dur-Pentatonik in der Lage über den Akkorden — passt auf alle vier. */
const PENTA = [72, 74, 76, 79, 81, 84]

/** Zufall, der sich wiederholen lässt (Tests, gleiche Takte nach Neustart). */
export function zufall(seed: number): () => number {
  let s = seed >>> 0 || 1
  return () => {
    s ^= s << 13
    s ^= s >>> 17
    s ^= s << 5
    return (s >>> 0) / 4294967296
  }
}

const achtel = (i: number) => i * 0.5 * SCHLAG + (i % 2 ? SWING * SCHLAG : 0)

/** Alles, was in Takt `nr` spielt (Zeiten relativ zum Taktanfang). */
export function takt(nr: number, rnd: () => number): Ereignis[] {
  const a = FOLGE[nr % FOLGE.length]!
  const out: Ereignis[] = []
  // Akkord auf der Eins, leicht gebrochen; manchmal ein leiser Nachschlag.
  a.toene.forEach((n, i) =>
    out.push({ stimme: 'akkord', t: i * 0.018, note: n, dauer: 2.6 * SCHLAG, vel: 0.55 }),
  )
  if (rnd() < 0.55)
    a.toene
      .slice(1)
      .forEach((n, i) =>
        out.push({ stimme: 'akkord', t: achtel(5) + i * 0.015, note: n, dauer: SCHLAG, vel: 0.3 }),
      )
  // Bass: Grundton auf der Eins, dazu Oktave oder Quinte auf der Drei.
  out.push({ stimme: 'bass', t: 0, note: a.bass, dauer: 1.6 * SCHLAG, vel: 0.8 })
  out.push({
    stimme: 'bass',
    t: 2.5 * SCHLAG + SWING * SCHLAG,
    note: a.bass + (rnd() < 0.5 ? 7 : 12),
    dauer: SCHLAG,
    vel: 0.6,
  })
  // Schlagzeug: Kick 1 und „3 und“, Snare 2 und 4, Hi-Hat auf allen Achteln.
  out.push({ stimme: 'kick', t: 0, dauer: 0.3, vel: 1 })
  out.push({ stimme: 'kick', t: achtel(5), dauer: 0.3, vel: 0.75 })
  if (rnd() < 0.3) out.push({ stimme: 'kick', t: achtel(3), dauer: 0.3, vel: 0.5 })
  out.push({ stimme: 'snare', t: SCHLAG, dauer: 0.2, vel: 0.9 })
  out.push({ stimme: 'snare', t: 3 * SCHLAG, dauer: 0.2, vel: 0.9 })
  for (let i = 0; i < 8; i++)
    if (rnd() > 0.08)
      out.push({ stimme: 'hihat', t: achtel(i), dauer: 0.05, vel: i % 2 ? 0.45 : 0.75 })
  // Melodie: wenige Töne, mit Pausen — mehr wäre Gedudel neben der Arbeit.
  if (nr % 8 >= 2) {
    for (let i = 1; i < 8; i += 1 + Math.floor(rnd() * 3)) {
      if (rnd() < 0.42) {
        const note = PENTA[Math.floor(rnd() * PENTA.length)]!
        out.push({ stimme: 'melodie', t: achtel(i), note, dauer: 0.9 * SCHLAG, vel: 0.5 })
      }
    }
  }
  return out
}

export const hz = (midi: number) => 440 * 2 ** ((midi - 69) / 12)
