import { hz, TAKT, takt, zufall, type Ereignis } from './klangMusik'

// Klänge im Construct-Raum. Alles entsteht hier mit der Web Audio API —
// keine Audiodateien: keine Lizenzfragen bei der Musik, nichts zu laden, und
// die Musik wiederholt sich nicht Takt für Takt.
//
// Browser lassen Ton erst nach einer Eingabe zu (Autoplay-Sperre). Bis zum
// ersten Klick oder Tastendruck bleibt es darum still; danach geht es los.

export interface KlangEinstellung {
  effekte: boolean
  musik: boolean
  /** 0–100 */
  lautstaerke: number
}

let ctx: AudioContext | null = null
let master: GainNode | null = null
let fxBus: GainNode | null = null
let musikBus: GainNode | null = null
let rauschen: AudioBuffer | null = null

let einst: KlangEinstellung = { effekte: false, musik: false, lautstaerke: 40 }
/** Raum sichtbar? Außerhalb des Raums bleibt alles still. */
let aktiv = false

function audio(): AudioContext | null {
  if (ctx) return ctx
  const AC =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AC) return null
  try {
    ctx = new AC()
  } catch {
    return null
  }
  master = ctx.createGain()
  master.connect(ctx.destination)
  fxBus = ctx.createGain()
  fxBus.gain.value = 0.9
  fxBus.connect(master)
  // Lo-Fi: die Musik bekommt oben herum etwas weggenommen.
  const warm = ctx.createBiquadFilter()
  warm.type = 'lowpass'
  warm.frequency.value = 3800
  warm.connect(master)
  musikBus = ctx.createGain()
  musikBus.gain.value = 0.32
  musikBus.connect(warm)
  const n = ctx.sampleRate
  rauschen = ctx.createBuffer(1, n, n)
  const d = rauschen.getChannelData(0)
  for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1
  lautstaerkeSetzen()
  // Läuft der Ton an (erster Klick) oder hält der Browser ihn an: neu prüfen.
  ctx.addEventListener('statechange', () => pruefen())
  return ctx
}

/** 0–100 → Verstärkung; quadratisch, weil das Ohr leise Stufen feiner hört. */
export const pegel = (prozent: number) => (Math.max(0, Math.min(100, prozent)) / 100) ** 2

function lautstaerkeSetzen() {
  if (!ctx || !master) return
  master.gain.setTargetAtTime(pegel(einst.lautstaerke), ctx.currentTime, 0.05)
}

let entsperrt = false
/** Einmal einrichten: beim ersten Klick/Tastendruck darf der Browser Ton. */
function entsperren() {
  if (entsperrt) return
  entsperrt = true
  const los = () => {
    const c = audio()
    if (c && c.state === 'suspended') void c.resume()
    removeEventListener('pointerdown', los, true)
    removeEventListener('keydown', los, true)
    pruefen()
  }
  addEventListener('pointerdown', los, true)
  addEventListener('keydown', los, true)
}

const laeuft = () => !!ctx && ctx.state === 'running'

// ---------------------------------------------------------------- Bausteine

function stoss(
  t: number,
  ziel: AudioNode,
  {
    dauer,
    vel,
    typ,
    freq,
    q = 1,
  }: { dauer: number; vel: number; typ: BiquadFilterType; freq: number; q?: number },
) {
  if (!ctx || !rauschen) return
  const src = ctx.createBufferSource()
  src.buffer = rauschen
  const f = ctx.createBiquadFilter()
  f.type = typ
  f.frequency.value = freq
  f.Q.value = q
  const g = ctx.createGain()
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(vel, t + 0.002)
  g.gain.exponentialRampToValueAtTime(0.0001, t + dauer)
  src.connect(f).connect(g).connect(ziel)
  src.start(t, Math.random() * 0.8, dauer + 0.05)
}

function ton(
  t: number,
  ziel: AudioNode,
  {
    freq,
    dauer,
    vel,
    typ = 'sine',
    anschlag = 0.005,
    bisFreq,
  }: {
    freq: number
    dauer: number
    vel: number
    typ?: OscillatorType
    anschlag?: number
    bisFreq?: number
  },
) {
  if (!ctx) return
  const o = ctx.createOscillator()
  o.type = typ
  o.frequency.setValueAtTime(freq, t)
  if (bisFreq) o.frequency.exponentialRampToValueAtTime(bisFreq, t + dauer * 0.8)
  const g = ctx.createGain()
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(vel, t + anschlag)
  g.gain.exponentialRampToValueAtTime(0.0001, t + dauer)
  o.connect(g).connect(ziel)
  o.start(t)
  o.stop(t + dauer + 0.05)
}

/** Rauschen, dessen Filter wandert — klingt wie ein Luftzug. */
function zug(t: number, von: number, bis: number, dauer: number, vel: number) {
  if (!ctx || !rauschen || !fxBus) return
  const src = ctx.createBufferSource()
  src.buffer = rauschen
  src.loop = true
  const f = ctx.createBiquadFilter()
  f.type = 'bandpass'
  f.Q.value = 0.9
  f.frequency.setValueAtTime(von, t)
  f.frequency.exponentialRampToValueAtTime(bis, t + dauer)
  const g = ctx.createGain()
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(vel, t + dauer * 0.35)
  g.gain.linearRampToValueAtTime(0, t + dauer)
  src.connect(f).connect(g).connect(fxBus)
  src.start(t)
  src.stop(t + dauer + 0.05)
}

// ---------------------------------------------------------------- Effekte

const effekt = () => aktiv && einst.effekte && laeuft()

let letzterTipp = 0
/** Tastenanschlag; `gross` = Leertaste/Enter, etwas tiefer und satter. */
export function tipp(gross = false, leiser = 1) {
  if (!effekt() || !ctx || !fxBus) return
  const t = ctx.currentTime
  if (t - letzterTipp < 0.025) return
  letzterTipp = t
  stoss(t, fxBus, {
    dauer: gross ? 0.05 : 0.032,
    vel: 0.32 * leiser,
    typ: 'bandpass',
    freq: (gross ? 1300 : 2200) + Math.random() * 900,
    q: 1.4,
  })
  ton(t, fxBus, { freq: gross ? 140 : 190, dauer: 0.03, vel: 0.12 * leiser, anschlag: 0.001 })
}

/** Etwas geht auf: Luftzug nach oben und ein leiser Zweiklang. */
export function oeffnen() {
  if (!effekt() || !ctx || !fxBus) return
  const t = ctx.currentTime
  zug(t, 450, 2600, 0.38, 0.22)
  ton(t + 0.1, fxBus, { freq: hz(76), dauer: 0.7, vel: 0.07, anschlag: 0.01 })
  ton(t + 0.16, fxBus, { freq: hz(83), dauer: 0.9, vel: 0.055, anschlag: 0.01 })
}

/** Etwas geht zu: Luftzug nach unten, ein tiefer Ton. */
export function schliessen() {
  if (!effekt() || !ctx || !fxBus) return
  const t = ctx.currentTime
  zug(t, 2200, 380, 0.32, 0.18)
  ton(t + 0.06, fxBus, { freq: hz(64), dauer: 0.5, vel: 0.055, anschlag: 0.01 })
}

/** Maus über einer Station — nur ein Hauch. */
export function streifen() {
  if (!effekt() || !ctx || !fxBus) return
  ton(ctx.currentTime, fxBus, { freq: 1480, dauer: 0.07, vel: 0.022, anschlag: 0.004 })
}

/** Durch den Monitor in den Chat: langer, steigender Sog. */
export function eintauchen() {
  if (!effekt() || !ctx || !fxBus) return
  const t = ctx.currentTime
  zug(t, 160, 5200, 1.0, 0.3)
  ton(t, fxBus, { freq: 70, bisFreq: 240, dauer: 1.0, vel: 0.14, anschlag: 0.3 })
}

// ---------------------------------------------------------------- Uhr

let uhrTimer: ReturnType<typeof setTimeout> | null = null
let tickTack = false

/** Ein Tick bzw. Tack, auf die Audio-Uhr genau zum Zeitpunkt `t` gelegt. */
function ticken(t: number) {
  if (!effekt() || !ctx || !fxBus) return
  tickTack = !tickTack
  stoss(t, fxBus, { dauer: 0.018, vel: 0.28, typ: 'highpass', freq: tickTack ? 3400 : 2500 })
}

/** Wann (Audio-Uhr) die nächste volle Sekunde zu HÖREN sein muss — die
 *  Ausgabeverzögerung des Geräts ist schon abgezogen. */
export function naechsteSekundeAudio(audioJetzt: number, msJetzt: number, latenz: number) {
  return audioJetzt + (1000 - (msJetzt % 1000)) / 1000 - latenz
}

/**
 * Tickende Uhr, solange sie offen ist. Kurz vor jeder vollen Sekunde wird der
 * Tick auf der Audio-Uhr eingeplant — so fällt er genau auf den Sprung der
 * Sekunde in der Anzeige (hooks/useSekunde.ts), statt mit dem Timer zu wackeln.
 */
export function uhr(an: boolean) {
  if (uhrTimer) clearTimeout(uhrTimer)
  uhrTimer = null
  if (!an) return
  const naechste = () => {
    const rest = 1000 - (Date.now() % 1000)
    // ~150 ms vorher aufwachen; ist die Sekunde schon zu nah, die übernächste.
    uhrTimer = setTimeout(
      () => {
        if (ctx) {
          const latenz = ctx.outputLatency || ctx.baseLatency || 0
          const t = naechsteSekundeAudio(ctx.currentTime, Date.now(), latenz)
          if (t > ctx.currentTime) ticken(t)
        }
        naechste()
      },
      rest > 200 ? rest - 150 : rest + 850,
    )
  }
  naechste()
}

// ---------------------------------------------------------------- Cody tippt

let codyTimer: ReturnType<typeof setTimeout> | null = null

/** Cody an der Werkbank: leises, unregelmäßiges Tippen mit Denkpausen. */
export function codyTippt(an: boolean) {
  if (codyTimer) clearTimeout(codyTimer)
  codyTimer = null
  if (!an) return
  let inFolge = 0
  const weiter = () => {
    const pause = inFolge > 8 + Math.random() * 20
    inFolge = pause ? 0 : inFolge + 1
    codyTimer = setTimeout(
      () => {
        tipp(Math.random() < 0.15, 0.45)
        weiter()
      },
      pause ? 500 + Math.random() * 1400 : 70 + Math.random() * 110,
    )
  }
  weiter()
}

// ---------------------------------------------------------------- Musik

let sitzung: GainNode | null = null
let planer: ReturnType<typeof setInterval> | null = null
let naechsterTakt = 0
let taktNr = 0
const rnd = zufall(Date.now())

function spiele(e: Ereignis, t0: number, ziel: AudioNode) {
  if (!ctx) return
  const t = t0 + e.t
  switch (e.stimme) {
    case 'akkord': {
      // Rhodes-artig: Sinus + leise Dreieck-Oktave, sanfter Ausklang.
      const f = hz(e.note!)
      ton(t, ziel, { freq: f, dauer: e.dauer, vel: 0.09 * e.vel, anschlag: 0.012 })
      ton(t, ziel, { freq: f * 2.003, dauer: e.dauer * 0.5, vel: 0.018 * e.vel, typ: 'triangle' })
      break
    }
    case 'bass':
      ton(t, ziel, { freq: hz(e.note!), dauer: e.dauer, vel: 0.28 * e.vel, anschlag: 0.01 })
      break
    case 'melodie':
      ton(t, ziel, {
        freq: hz(e.note!),
        dauer: e.dauer,
        vel: 0.05 * e.vel,
        typ: 'triangle',
        anschlag: 0.02,
      })
      break
    case 'kick':
      ton(t, ziel, { freq: 115, bisFreq: 42, dauer: 0.28, vel: 0.5 * e.vel, anschlag: 0.003 })
      break
    case 'snare':
      stoss(t, ziel, { dauer: 0.16, vel: 0.16 * e.vel, typ: 'bandpass', freq: 1700, q: 0.7 })
      ton(t, ziel, { freq: 185, dauer: 0.07, vel: 0.08 * e.vel, anschlag: 0.002 })
      break
    case 'hihat':
      stoss(t, ziel, { dauer: 0.04, vel: 0.07 * e.vel, typ: 'highpass', freq: 7200 })
      break
  }
}

/** Plattenknistern: leises Rauschen dauerhaft, darauf vereinzelte Knackser. */
function knistern(ziel: AudioNode) {
  if (!ctx || !rauschen) return
  const src = ctx.createBufferSource()
  src.buffer = rauschen
  src.loop = true
  const f = ctx.createBiquadFilter()
  f.type = 'bandpass'
  f.frequency.value = 2500
  f.Q.value = 0.4
  const g = ctx.createGain()
  g.gain.value = 0.012
  src.connect(f).connect(g).connect(ziel)
  src.start()
}

function planen() {
  if (!ctx || !sitzung) return
  // Im Hintergrund drosselt der Browser Timer bis auf einmal pro Minute —
  // dann weit genug im Voraus planen, damit die Musik keine Lücken bekommt.
  const voraus = document.hidden ? 70 : 1.5
  while (naechsterTakt < ctx.currentTime + voraus) {
    for (const e of takt(taktNr, rnd)) spiele(e, naechsterTakt, sitzung)
    if (rnd() < 0.6) {
      const t = naechsterTakt + rnd() * TAKT
      stoss(t, sitzung, { dauer: 0.006, vel: 0.05, typ: 'highpass', freq: 1500 })
    }
    naechsterTakt += TAKT
    taktNr++
  }
}

function musikStarten() {
  if (sitzung || !ctx || !musikBus) return
  sitzung = ctx.createGain()
  sitzung.gain.setValueAtTime(0, ctx.currentTime)
  sitzung.gain.linearRampToValueAtTime(1, ctx.currentTime + 3)
  sitzung.connect(musikBus)
  knistern(sitzung)
  naechsterTakt = ctx.currentTime + 0.1
  planen()
  planer = setInterval(planen, 250)
  addEventListener('visibilitychange', planen)
}

function musikStoppen() {
  if (planer) clearInterval(planer)
  planer = null
  removeEventListener('visibilitychange', planen)
  const alt = sitzung
  sitzung = null
  if (!alt || !ctx) return
  // Ausblenden und dann abklemmen — das nimmt auch alles schon Geplante mit.
  alt.gain.cancelScheduledValues(ctx.currentTime)
  alt.gain.setTargetAtTime(0, ctx.currentTime, 0.25)
  setTimeout(() => alt.disconnect(), 1500)
}

// ---------------------------------------------------------------- Steuerung

function pruefen() {
  const musikSoll = aktiv && einst.musik && laeuft()
  if (musikSoll) musikStarten()
  else musikStoppen()
  if (!(aktiv && einst.effekte)) {
    uhr(false)
    codyTippt(false)
  }
}

/** Einstellungen übernehmen (aus ⚙ bzw. dem Lautsprecher-Knopf im Raum). */
export function klangEinstellen(neu: KlangEinstellung) {
  einst = { ...neu }
  if (ctx) lautstaerkeSetzen()
  pruefen()
}

/** Raum betreten bzw. verlassen. */
export function klangAktiv(an: boolean) {
  aktiv = an
  if (an) {
    entsperren()
    const c = audio()
    // Wer schon geklickt hat (z. B. auf „Raum“), darf sofort hören.
    if (c && c.state === 'suspended' && navigator.userActivation?.hasBeenActive) void c.resume()
  }
  pruefen()
}
