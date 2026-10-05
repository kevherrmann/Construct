import type { Kamera, Punkt } from './kamera'

// Stationen des Construct-Raums: Flächen auf dem Raumbild (assets/raum.webp,
// 16:9) in Prozent, damit sie mit der Bühne mitskalieren. Ausgemessen mit
// einer Überlagerung auf dem Bild (construct-raum-art/stationen.json).

export type StationId =
  | 'klemmbrett'
  | 'regal'
  | 'archiv'
  | 'monitore'
  | 'uhr'
  | 'kalender'
  | 'werkzeug'
  | 'steckfeld'
  | 'werkbank'
  | 'postfach'
  | 'pult'
  | 'tafel'
  | 'firma'

/** Links, oben, Breite, Höhe in Prozent der Bühne. */
export interface Rechteck {
  l: number
  t: number
  w: number
  h: number
}

export interface Station extends Rechteck {
  id: StationId
  /** Deutscher Schlüssel, übersetzt beim Zeichnen. */
  label: string
  /** Was man dort tut — Untertitel im Hinweis. */
  hint: string
  /** Was aufgeht. 'chat' = durch den Monitor in die Chat-Ansicht. */
  panel: Ansicht | 'chat'
}

export type PanelId =
  | 'uhr'
  | 'projekte'
  | 'sessions'
  | 'kalender'
  | 'skills'
  | 'mcp'
  | 'werkbank'
  | 'mail'
  | 'ausruestung'
  | 'tickets'
  /** Team-Modus: die Mitarbeiter und die Aufträge der Firma. */
  | 'personal'
  | 'auftraege'
  /** Ohne eigene Station: ⚙ oben rechts, die Kamera geht zum Pult. */
  | 'einstellungen'

// Reihenfolge = Stapelung: spätere liegen oben (Werkzeugwand über Werkbank).
export const STATIONEN: Station[] = [
  // Team-Modus: der Büroboden zwischen den Schreibtischen. Ganz unten, damit die
  // Sitze (eigene Knöpfe) und die Wandobjekte davor Vorrang haben.
  {
    id: 'firma',
    l: 28.5,
    t: 25.5,
    w: 14,
    h: 27.5,
    label: 'Firma',
    hint: 'Aufträge der Firma',
    panel: 'auftraege',
  },
  {
    id: 'regal',
    l: 0,
    t: 5.5,
    w: 20.6,
    h: 60,
    label: 'Projekte',
    hint: 'Arbeitsordner wählen',
    panel: 'projekte',
  },
  {
    id: 'archiv',
    l: 20.3,
    t: 19.4,
    w: 6.1,
    h: 30,
    label: 'Sessions',
    hint: 'Frühere Gespräche öffnen',
    panel: 'sessions',
  },
  {
    id: 'monitore',
    l: 48,
    t: 9.7,
    w: 29.7,
    h: 24.3,
    label: 'Chat-Ansicht',
    hint: 'Durch den Monitor in den vollen Chat',
    panel: 'chat',
  },
  {
    id: 'werkbank',
    l: 69.5,
    t: 45,
    w: 27,
    h: 36,
    label: 'Werkbank',
    hint: 'Geänderte Dateien',
    panel: 'werkbank',
  },
  // Klemmbrett auf der Werkbank: liegt über ihr, darum danach.
  {
    id: 'klemmbrett',
    l: 82.8,
    t: 55.2,
    w: 4.9,
    h: 5.0,
    label: 'Protokoll',
    hint: 'Der ganze Verlauf dieser Session',
    panel: 'protokoll',
  },
  {
    id: 'werkzeug',
    l: 80.3,
    t: 27.6,
    w: 11.2,
    h: 22,
    label: 'Skills',
    hint: 'Wiederverwendbare Routinen',
    panel: 'skills',
  },
  {
    id: 'uhr',
    l: 91,
    t: 18.4,
    w: 5,
    h: 10,
    label: 'Uhr',
    hint: 'Uhrzeit und was als Nächstes kommt',
    panel: 'uhr',
  },
  {
    id: 'kalender',
    l: 92.3,
    t: 34.5,
    w: 5.6,
    h: 15,
    label: 'Kalender',
    hint: 'Termine',
    panel: 'kalender',
  },
  {
    id: 'steckfeld',
    l: 94.6,
    t: 50.8,
    w: 4.6,
    h: 12,
    label: 'MCP',
    hint: 'Verbundene Dienste',
    panel: 'mcp',
  },
  {
    id: 'postfach',
    l: 10.2,
    t: 67,
    w: 12.8,
    h: 26,
    label: 'E-Mails',
    hint: 'Posteingang',
    panel: 'mail',
  },
  {
    id: 'tafel',
    l: 23.462,
    t: 54.688,
    w: 8.74,
    h: 21.701,
    label: 'Tickets',
    hint: 'Aufgaben nach Tag und Projekt',
    panel: 'tickets',
  },
  {
    id: 'pult',
    l: 48.6,
    t: 50,
    w: 3.2,
    h: 22.5,
    label: 'Modell & Modus',
    hint: 'Was geladen wird',
    panel: 'ausruestung',
  },
]

/** Wo die Figur in den Quellbildern steht: Fußpunkt (Mitte unten) und Höhe,
 *  in Prozent der Bühne. Danach sind die Posen-Videos geschnitten. */
const FIGUR_QUELLE = { x: 45.65, y: 75.7, h: 40.8 }
/** So gerechnet wäre die Figur auf dem Podest kleiner als an der Werkbank
 *  (466 statt 546 px im Raumbild). Standbild und Video wachsen darum
 *  gemeinsam um den Fußpunkt, die Füße bleiben auf dem Podest. */
const PODEST_ZOOM = 1.15

/** Wo die Figur auf dem Podest steht: Fußpunkt und Höhe in Prozent der Bühne. */
export const FIGUR = { ...FIGUR_QUELLE, h: FIGUR_QUELLE.h * PODEST_ZOOM }

/** Ausschnitt um den Fußpunkt vergrößern (wie die Figur). */
const umFuss = (r: Rechteck): Rechteck => ({
  l: FIGUR_QUELLE.x + (r.l - FIGUR_QUELLE.x) * PODEST_ZOOM,
  t: FIGUR_QUELLE.y + (r.t - FIGUR_QUELLE.y) * PODEST_ZOOM,
  w: r.w * PODEST_ZOOM,
  h: r.h * PODEST_ZOOM,
})

/** Form je Station (assets/form/<id>.webp): Bereich in Prozent. Beim
 *  Überfahren stellt die Kamera darauf scharf, der Rest wird unscharf. */
export const FORM: Record<StationId, Rechteck> = {
  klemmbrett: { l: 80.566, t: 52.083, w: 9.277, h: 13.889 },
  regal: { l: 0.0, t: 3.385, w: 21.777, h: 64.236 },
  archiv: { l: 19.092, t: 17.274, w: 8.496, h: 34.288 },
  monitore: { l: 46.777, t: 7.552, w: 32.129, h: 28.559 },
  werkbank: { l: 68.848, t: 35.069, w: 28.906, h: 46.701 }, // mit Monitor + Tastatur
  werkzeug: { l: 79.102, t: 25.434, w: 13.574, h: 26.302 },
  uhr: { l: 89.795, t: 16.233, w: 7.422, h: 14.323 },
  kalender: { l: 91.113, t: 32.378, w: 8.008, h: 19.271 },
  steckfeld: { l: 93.408, t: 48.698, w: 6.592, h: 16.233 },
  postfach: { l: 8.984, t: 64.844, w: 15.234, h: 30.295 },
  pult: { l: 47.412, t: 47.83, w: 5.566, h: 26.823 },
  // Hologramm ohne Bildmaske (kein Gegenstand im Raumbild): nur die Fläche.
  tafel: { l: 23.462, t: 54.688, w: 8.74, h: 21.701 },
  firma: { l: 28.5, t: 25.5, w: 14, h: 27.5 },
}

/** Wanduhr: Zifferblatt als Einheitskreis → Raumbild (Pixel, affin;
 *  SVG-matrix a b c d e f). Ausgemessen an den Marken 12, 3, 6 und 9. */
export const UHR_MATRIX = [33, 12, -3.5, 42, 1909.75, 272] as const

/** Projektname unter dem Regal, in der Ebene der Regalfront (Pixel im
 *  Raumbild: oben links, oben rechts, unten rechts, unten links). Die
 *  Unterkante des Regals läuft von (0, 765) nach (430, 577); rechts kleiner,
 *  weil das Regal dort weiter weg ist. */
export const REGAL_SCHILD: readonly [Punkt, Punkt, Punkt, Punkt] = [
  [70, 751],
  [340, 631],
  [340, 685],
  [70, 815],
]

// Ausschnitte aus dem Raumbild (2048×1152 px), in denen Ebenen liegen:
// Posen-Videos am Podest (655,300 – 1215,1000) und die Werkbank-Ebenen mit
// Figur bzw. Monitor + Tastatur (1120,266 – 1888,1098; oben Platz für den
// Kopf). Das Tipp-Video an der Werkbank hat denselben Ausschnitt.
export const PODEST_VIDEO: Rechteck = umFuss({ l: 31.982, t: 26.042, w: 27.344, h: 60.764 })
export const WERKBANK: Rechteck = { l: 54.688, t: 23.09, w: 37.5, h: 72.222 }

/** Kontingent-Anzeige an der Wand links neben der Uhr, über der Lochwand
 *  (Pixel im Raumbild: oben links, oben rechts, unten links). Oberkante im
 *  Winkel der Wand wie die Lochwand, die Senkrechte kippt wie bei der Uhr. */
export const WAND_KONTINGENT: readonly [Punkt, Punkt, Punkt] = [
  [1650, 140],
  [1846, 211],
  [1647, 296],
]

/** Der Karteikasten der Tickets samt Schatten (Ebene, Prozent der Bühne). */
export const KASTEN: Rechteck = { l: 21.997, t: 52.083, w: 11.67, h: 26.91 }

/** Die Monitorwand: Fläche, auf der der Terminal-Text liegt (oben links,
 *  oben rechts, unten rechts, unten links; Prozent). Etwas größer als die
 *  Bildschirme — die genaue, gebogene Form gibt assets/fernseher-maske.webp vor. */
export const FERNSEHER: readonly [Punkt, Punkt, Punkt, Punkt] = [
  [48.096, 9.722],
  [77.734, 15.451],
  [77.734, 34.896],
  [48.096, 28.212],
]
/** Größe der Terminalfläche: so groß, wie sie bei diesem Zoom auf dem
 *  Bildschirm wäre — der Text bleibt beim Hineinfahren scharf. */
export const FERNSEHER_ZOOM = 2.5

/** Kamera „durch den Monitor“: so nah, dass die Bildschirme alles füllen. */
export const EINTAUCHEN: Kamera = { z: 5.8, f: [62.9, 22.1], p: [50, 50] }

/** Klemmbrett auf der Werkbank (Ebene, Prozent). */
export const KLEMMBRETT: Rechteck = { l: 80.566, t: 52.083, w: 9.277, h: 13.889 }

/** Rand der Schein-Masken (assets/schein) um die Form, in Prozent. */
export const SCHEIN_RAND = { x: 1.172, y: 2.083 }

/** Was im Raum aufgehen kann: jede Station und das Protokoll. */
export type Ansicht = PanelId | 'protokoll'

export interface Auftritt extends Kamera {
  /** Auf welcher Seite der Inhalt im Weiß erscheint (null = auf dem Fernseher). */
  seite: 'links' | 'rechts' | null
  /** Breite des Inhalts in Prozent der Bühne. */
  breite: number
  /** Ziel der Leitlinie: die Station im Raum (Prozent). */
  ziel: Punkt
}

// Kamerafahrt je Ansicht: Station `f` landet bei `p` auf dem Bildschirm, der
// Inhalt erscheint auf der anderen Seite. Schmale Listen bleiben schmal.
export const AUFTRITT: Record<Ansicht, Auftritt> = {
  projekte: { z: 1.7, f: [10.3, 36], p: [19, 50], seite: 'rechts', breite: 36, ziel: [10.3, 36] },
  sessions: { z: 1.8, f: [23.4, 34], p: [22, 48], seite: 'rechts', breite: 36, ziel: [23.4, 34] },
  werkbank: { z: 1.55, f: [80, 58], p: [76, 56], seite: 'links', breite: 38, ziel: [78, 55] },
  skills: { z: 1.6, f: [85.9, 38.6], p: [80, 46], seite: 'links', breite: 58, ziel: [85.9, 38.6] },
  kalender: { z: 1.6, f: [94, 38], p: [84, 46], seite: 'links', breite: 60, ziel: [95.1, 42] },
  uhr: { z: 2.2, f: [93.2, 23.6], p: [82, 42], seite: 'links', breite: 50, ziel: [93.2, 23.6] },
  mcp: { z: 1.8, f: [96.9, 56.8], p: [84, 52], seite: 'links', breite: 38, ziel: [96.9, 56.8] },
  mail: { z: 1.5, f: [16.6, 78], p: [17, 60], seite: 'rechts', breite: 62, ziel: [16.6, 78] },
  ausruestung: { z: 1.35, f: [48, 52], p: [26, 55], seite: 'rechts', breite: 46, ziel: [50.2, 58] },
  tickets: { z: 1.5, f: [27.5, 66], p: [21, 52], seite: 'rechts', breite: 50, ziel: [27.5, 66] },
  personal: { z: 1.6, f: [46, 36], p: [24, 52], seite: 'rechts', breite: 52, ziel: [46, 36] },
  auftraege: { z: 1.6, f: [46, 36], p: [24, 52], seite: 'rechts', breite: 56, ziel: [46, 36] },
  einstellungen: {
    z: 1.2,
    f: [50.2, 58],
    p: [25, 60],
    seite: 'rechts',
    breite: 54,
    ziel: [50.2, 58],
  },
  // Protokoll: die Kamera geht zum Klemmbrett auf der Werkbank
  protokoll: {
    z: 1.55,
    f: [85.2, 57.6],
    p: [80, 56],
    seite: 'links',
    breite: 46,
    ziel: [85.2, 57.6],
  },
}

// ---------- Büro der Firma (Team-Modus) ----------

/** Maße der Bühne in Pixeln — die Raumbilder sind 2048 × 1152. */
export const BUERO_BUEHNE = { w: 2048, h: 1152 }

/** Ein Ort im Raum: Fußpunkt (Mitte unten, Pixel auf dem Raumbild) und Maßstab
 *  (je weiter hinten, desto kleiner). */
export interface Platz {
  x: number
  y: number
  s: number
}

export type PaarId = 'a' | 'b'
export type Seite = 'links' | 'rechts'

/** Die Doppelschreibtische stehen in der freien Ecke zwischen Aktenschrank und
 *  Podest — nicht vor dem Fernseher. Zwei Leute sitzen sich gegenüber: einer links,
 *  einer rechts. Fußpunkt = Mitte der Vorderkante. */
export const PAARE: Record<PaarId, Platz> = {
  a: { x: 715, y: 562, s: 0.85 },
  b: { x: 680, y: 422, s: 0.72 },
}

/** Wer an welchem Doppelschreibtisch sitzt (nach Kürzel): für diese vier gibt es
 *  Bilder von Tisch und Werkbank. Alle anderen bekommen einen Platz am Rand. */
export const SITZE: Record<string, { paar: PaarId; seite: Seite }> = {
  cody: { paar: 'a', seite: 'links' },
  selma: { paar: 'a', seite: 'rechts' },
  tessa: { paar: 'b', seite: 'links' },
  veritas: { paar: 'b', seite: 'rechts' },
}

/** Das Tischbild: 757 × 560 px mit 20 px Rand für den Standschatten (Inhalt
 *  717 × 520); bei Maßstab 1 steht der Inhalt DOPPEL_HOEHE Pixel hoch im Raum. */
export const DOPPEL = { w: 757, h: 560, rand: 20, inhaltW: 717, inhaltH: 520 }
export const DOPPEL_HOEHE = 235

/** Fußpunkte der beiden Stühle im Tischbild (Anteil an Breite/Höhe des Inhalts). */
const STUHL_FUSS: Record<Seite, { x: number; y: number }> = {
  links: { x: 0.16, y: 0.86 },
  rechts: { x: 0.84, y: 0.86 },
}

/** Wo ein Sitz im Raum steht (Fußpunkt des Stuhls, Pixel), samt Maßstab. */
export function sitzFuss(paar: PaarId, seite: Seite): Platz {
  const p = PAARE[paar]
  const k = (DOPPEL_HOEHE / DOPPEL.inhaltH) * p.s
  const f = STUHL_FUSS[seite]
  return {
    x: p.x + (f.x - 0.5) * DOPPEL.inhaltW * k,
    y: p.y - (1 - f.y) * DOPPEL.inhaltH * k,
    s: p.s,
  }
}

/** Plätze für Mitarbeiter ohne Doppelschreibtisch (zum Beispiel ein später
 *  Eingestellter): ihr Profilbild steht dort. */
export const RANDPLAETZE: readonly Platz[] = [
  { x: 610, y: 330, s: 0.7 },
  { x: 560, y: 345, s: 0.7 },
]

/** Wo an der Werkbank die Füße stehen (Pixel auf dem Raumbild): dort läuft ein
 *  Mitarbeiter hin, wenn er arbeitet. */
export const WERKBANK_FUSS = { x: 1470, y: 892 }
