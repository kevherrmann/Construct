import { helferOffen } from '@/lib/chat/helfer'
import type { Helfer } from '@/lib/chat/types'
import { werkzeugStation } from './lage'
import {
  BUERO_BUEHNE,
  FIGUR,
  PAARE,
  WERKBANK,
  WERKBANK_FUSS,
  massstab,
  type PaarId,
  type Platz,
  type Rechteck,
} from './stationen'

// Helfer (Agent/Task) als Hologramme im Raum: welche gerade zu sehen sind, in
// welcher Phase und wo sie stehen. Rein, ohne Oberfläche (wie lage.ts): die Zeit
// kommt von außen, der Raum ruft holosNach bei jeder Änderung und zum nächsten
// Zeitpunkt aus naechsteAenderung erneut auf.

/** Aufbau aus Scanlinien neben dem Besitzer. Muss zur Animation im CSS passen. */
export const ERSCHEINEN_MS = 800
/** Zerfall in Code-Regen samt Blatt, das zum Besitzer schwebt. */
export const ZERFALL_MS = 1600
/** So lange bleibt es mindestens an einer Station, damit auch ein kurzer Abstecher
 *  zu sehen ist. Wechselt das Werkzeug schneller, zählt danach nur der neueste Ort. */
export const VERWEILEN_MS = 4000
/** Fehler: kurzes Ausflackern. */
export const FLACKERN_MS = 700
/** So viele stehen gleichzeitig im Raum, weitere zählt ein „+N“. */
export const PLAETZE = 4

export type HoloPhase = 'erscheint' | 'arbeitet' | 'zerfaellt' | 'flackert'
/** Wo ein Hologramm steht: neben seinem Besitzer oder an einer Station. */
export type HoloOrt = 'neben' | 'regal' | 'werkbank'

export interface Holo {
  id: string
  beschreibung: string
  detail: string
  werkzeug: string
  phase: HoloPhase
  /** Beginn der Phase (ms). */
  seit: number
  /** Platz 0 … PLAETZE-1; -1 = wartet auf einen freien (zählt zum „+N“). */
  platz: number
  ort: HoloOrt
  /** Seit wann es an diesem Ort steht (ms). */
  ortSeit: number
}

/** Station eines Werkzeugs → Ort im Raum. Ohne eigene Station bleibt es stehen. */
export function ortVon(werkzeug: string): HoloOrt {
  if (!werkzeug) return 'neben'
  const st = werkzeugStation(werkzeug)
  if (!st || st === 'firma') return 'neben'
  if (st === 'regal' || st === 'archiv' || st === 'tafel') return 'regal'
  return 'werkbank'
}

const DAUER: Partial<Record<HoloPhase, number>> = {
  erscheint: ERSCHEINEN_MS,
  zerfaellt: ZERFALL_MS,
  flackert: FLACKERN_MS,
}
const endet = (h: Holo) => h.phase === 'zerfaellt' || h.phase === 'flackert'

/** Ab wann es an die Station seines Werkzeugs geht (null = es steht schon richtig).
 *  Neben dem Besitzer ist keine Station: von dort geht es sofort los. */
function wechselAb(h: Holo): number | null {
  if (h.phase !== 'arbeitet' || h.ort === ortVon(h.werkzeug)) return null
  return h.ort === 'neben' ? h.ortSeit : h.ortSeit + VERWEILEN_MS
}
const gleich = (a: Holo, b: Holo) => (Object.keys(a) as (keyof Holo)[]).every((k) => a[k] === b[k])

/**
 * Hologramme nach dem Stand der Helfer. Was aus der Liste verschwindet (der Lauf
 * ist vorbei und mit ihm die Liste), zerfällt wie ein fertiger Helfer. Unbekannte,
 * die schon fertig sind, erscheinen gar nicht erst. Ändert sich nichts, kommt
 * dieselbe Liste zurück.
 */
export function holosNach(vorher: Holo[], helfer: readonly Helfer[], jetzt: number): Holo[] {
  const nachId = new Map(helfer.map((h) => [h.id, h]))
  const out: Holo[] = []
  for (const alt of vorher) {
    const h = nachId.get(alt.id)
    let neu: Holo = h
      ? { ...alt, beschreibung: h.beschreibung, detail: h.detail, werkzeug: h.werkzeug }
      : alt
    const vorbei = jetzt - neu.seit >= (DAUER[neu.phase] ?? Infinity)
    if (endet(neu)) {
      if (vorbei || neu.platz < 0) continue // ausgespielt bzw. nie zu sehen gewesen
    } else if (!h || h.stand === 'fertig') {
      if (neu.platz < 0) continue
      neu = { ...neu, phase: 'zerfaellt', seit: jetzt }
    } else if (h.stand === 'fehler') {
      if (neu.platz < 0) continue
      neu = { ...neu, phase: 'flackert', seit: jetzt }
    } else if (neu.phase === 'erscheint' && vorbei) {
      neu = { ...neu, phase: 'arbeitet', seit: neu.seit + ERSCHEINEN_MS }
    }
    // An die Station erst, wenn es ganz da ist, und erst nach der Verweilzeit an der
    // vorigen; beim Zerfallen bleibt es, wo es war.
    // Solange es noch bleibt, behält es die Zeile seines Orts: „Editing“ am Regal
    // passt nicht zum Bild.
    const ab = wechselAb(neu)
    if (ab !== null && jetzt >= ab) neu = { ...neu, ort: ortVon(neu.werkzeug), ortSeit: jetzt }
    else if (ab !== null) neu = { ...neu, detail: alt.detail }
    out.push(gleich(neu, alt) ? alt : neu)
  }
  for (const h of helfer) {
    if (!helferOffen(h) || vorher.some((v) => v.id === h.id)) continue
    out.push({
      id: h.id,
      beschreibung: h.beschreibung,
      detail: h.detail,
      werkzeug: h.werkzeug,
      phase: 'erscheint',
      seit: jetzt,
      platz: -1,
      ort: 'neben',
      ortSeit: jetzt,
    })
  }
  // Wartende rücken auf freie Plätze nach, in der Reihenfolge ihres Starts.
  const belegt = new Set(out.filter((h) => h.platz >= 0).map((h) => h.platz))
  for (let i = 0; i < out.length; i++) {
    const h = out[i]!
    if (h.platz >= 0 || endet(h)) continue
    let p = 0
    while (belegt.has(p)) p++
    if (p >= PLAETZE) break
    belegt.add(p)
    out[i] = { ...h, platz: p, phase: 'erscheint', seit: jetzt, ort: 'neben', ortSeit: jetzt }
  }
  return out.length === vorher.length && out.every((h, i) => h === vorher[i]) ? vorher : out
}

/** In wie vielen ms sich ohne neues Ereignis etwas ändert (null = nie). */
export function naechsteAenderung(holos: readonly Holo[], jetzt: number): number | null {
  let min: number | null = null
  for (const h of holos) {
    if (h.platz < 0) continue
    const d = DAUER[h.phase]
    const ab = d === undefined ? wechselAb(h) : h.seit + d
    if (ab === null) continue
    const rest = Math.max(0, ab - jetzt)
    if (min === null || rest < min) min = rest
  }
  return min
}

/** Wie viele warten, weil alle Plätze besetzt sind. */
export const wartende = (holos: readonly Holo[]) => holos.filter((h) => h.platz < 0).length

// ---------- Aufstellung ----------

/** Ein Hologramm im Raum: eine Pose am Fußpunkt (wie die Figur am Podest) oder
 *  das Bild an der Werkbank in einer Fläche. Prozent der Bühne. */
export type Stellung =
  | { art: 'pose'; pose: 'idle' | 'lesen'; x: number; y: number; h: number }
  | { art: 'werkbank'; r: Rechteck }

const PX_Y = BUERO_BUEHNE.h / 100
/** Höhe der Figur, wenn ihre Füße bei y (Prozent) stehen. */
const hoeheBei = (y: number) => FIGUR.h * massstab(y * PX_Y, FIGUR.y * PX_Y)

/** Neben dem Podest: schräg nach links vorn versetzt, weg von Pult und Sprechblase
 *  (die rechts steht); keiner verdeckt den anderen. */
const NEBEN: readonly [number, number][] = [
  [36.6, 73.4],
  [29.4, 77.8],
  [22.2, 82.2],
  [15, 86.6],
]
/** Vor dem Regal, das Tablet in der Hand. */
const AM_REGAL: readonly [number, number][] = [
  [22.6, 71.2],
  [15.2, 75.4],
]
/** Neben der Werkbank, wenn dort schon jemand tippt. */
const VOR_WERKBANK: readonly [number, number][] = [
  [64.2, 81],
  [60.4, 88.4],
]
/** Ein Stück weiter rechts an der Werkbank (zweiter Platz zum Tippen). Ihre
 *  Vorderkante läuft schräg nach vorn: je 100 px nach rechts 55 px nach unten. */
const WERKBANK_RECHTS = verschiebe(WERKBANK, 9.6, 9.4)

/** Werkbank-Fläche verschoben (Prozent), mit der Perspektive größer bzw. kleiner. */
function verschiebe(r: Rechteck, dx: number, dy: number): Rechteck {
  const k = massstab(WERKBANK_FUSS.y + dy * PX_Y, WERKBANK_FUSS.y)
  const fx = r.l + r.w * (350 / 768)
  const fy = r.t + r.h * (626 / 832)
  return {
    l: fx + dx - (fx - r.l) * k,
    t: fy + dy - (fy - r.t) * k,
    w: r.w * k,
    h: r.h * k,
  }
}

const pose = (p: 'idle' | 'lesen', [x, y]: readonly [number, number]): Stellung => ({
  art: 'pose',
  pose: p,
  x,
  y,
  h: hoeheBei(y),
})

/**
 * Wo die Hologramme des Assistenten stehen. `werkbankFrei`: an der Werkbank tippt
 * gerade niemand (weder die Figur noch ein Mitarbeiter), der erste Helfer dort
 * bekommt ihren Platz. Mehrere am selben Ort stehen versetzt.
 */
export function aufstellung(holos: readonly Holo[], werkbankFrei: boolean): Map<string, Stellung> {
  const out = new Map<string, Stellung>()
  const zaehler: Record<HoloOrt, number> = { neben: 0, regal: 0, werkbank: 0 }
  const sichtbar = holos.filter((h) => h.platz >= 0).sort((a, b) => a.platz - b.platz)
  for (const h of sichtbar) {
    const i = zaehler[h.ort]++
    if (h.ort === 'neben') out.set(h.id, pose('idle', NEBEN[h.platz]!))
    else if (h.ort === 'regal') out.set(h.id, pose('lesen', AM_REGAL[i % AM_REGAL.length]!))
    else {
      const tippen = werkbankFrei ? [WERKBANK, WERKBANK_RECHTS] : [WERKBANK_RECHTS]
      out.set(
        h.id,
        i < tippen.length
          ? { art: 'werkbank', r: tippen[i]! }
          : pose('lesen', VOR_WERKBANK[(i - tippen.length) % VOR_WERKBANK.length]!),
      )
    }
  }
  return out
}

/** Wo „+N“ steht: hinter dem letzten Platz neben dem Podest. */
export const PLUS_ORT = { x: NEBEN[3]![0] - 5.6, y: NEBEN[3]![1] - 2 }

/** Brusthöhe einer Stellung: dort startet das Blatt. */
export function brust(st: Stellung): { x: number; y: number } {
  if (st.art === 'pose') return { x: st.x, y: st.y - st.h * 0.62 }
  return { x: st.r.l + st.r.w * (350 / 768), y: st.r.t + st.r.h * 0.34 }
}

/** Brust der Figur selbst: am Podest bzw. an der Werkbank. */
export const BRUST_PODEST = { x: FIGUR.x, y: FIGUR.y - FIGUR.h * 0.62 }
export const BRUST_WERKBANK = brust({ art: 'werkbank', r: WERKBANK })

/** Neben einem Mitarbeiter an der Werkbank, wenn ihr zweiter Platz schon belegt ist:
 *  links hinter ihm zwischen Podest und Werkbank, gestaffelt (Pixel im Raumbild). */
const HINTER_WERKBANK: readonly [number, number][] = [
  [1300, 772],
  [1226, 716],
]

/** Bild von der Werkbank (768 × 832, Füße bei 350, 626, dort 1 : 1) mit den Füßen
 *  bei x, y (Pixel im Raumbild), in der Perspektive verkleinert. */
function werkbildBei(x: number, y: number): Rechteck {
  const k = massstab(y, WERKBANK_FUSS.y)
  return {
    l: ((x - 350 * k) / BUERO_BUEHNE.w) * 100,
    t: ((y - 626 * k) / BUERO_BUEHNE.h) * 100,
    w: ((768 * k) / BUERO_BUEHNE.w) * 100,
    h: ((832 * k) / BUERO_BUEHNE.h) * 100,
  }
}

/**
 * Hologramme eines Mitarbeiters: sein Bild von der Werkbank, neben ihm. Steht er an
 * der Werkbank, tippt der erste am Platz rechts neben ihm, weitere stehen links hinter ihm. Sitzt er am Doppelschreibtisch, stehen
 * sie außen neben dem Tisch (links vom linken, rechts vom rechten), damit sie keinen
 * Kollegen verdecken; wer am Rand sitzt, hat sie links neben sich.
 */
export function nebenMitarbeiter(
  amWerk: boolean,
  sitz: { platz: Platz; paar?: PaarId },
  i: number,
): Rechteck {
  if (amWerk) {
    // der erste tippt am zweiten Platz der Werkbank, wie ein Kollege neben ihm
    if (i === 0) return WERKBANK_RECHTS
    const [x, y] = HINTER_WERKBANK[Math.min(i - 1, HINTER_WERKBANK.length - 1)]!
    return werkbildBei(x, y)
  }
  if (!sitz.paar) return werkbildBei(sitz.platz.x - (90 + i * 80) * sitz.platz.s, sitz.platz.y + 8)
  const tisch = PAARE[sitz.paar]
  const aussen = tisch.x < BUERO_BUEHNE.w / 2 ? -1 : 1
  return werkbildBei(tisch.x + aussen * (262 + i * 78) * tisch.s, tisch.y + 6 - i * 6)
}
