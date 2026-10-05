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
  /** Klickbare Form als Vieleck in Prozent der Fläche (sonst das ganze Rechteck). */
  form?: readonly (readonly [number, number])[]
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

// Die Wand rechts über Lochwand und Kalender: Binäruhr und darunter das Kontingent.
// Beide werden in einem festen Maß (Design-Pixel) gezeichnet und flach verzerrt auf
// die Wand gelegt. Waagerecht im Winkel der Lochwand, die Senkrechte kippt leicht.
const WAND = { o: [1650, 206], u: [0.49, 0.1775], v: [-0.012, 0.488] } as const
/** Punkt auf der Wand (Design-Pixel) → Raumbild-Pixel. */
const aufWand = (x: number, y: number): Punkt => [
  WAND.o[0] + x * WAND.u[0] + y * WAND.v[0],
  WAND.o[1] + x * WAND.u[1] + y * WAND.v[1],
]
/** Parallelogramm (oben links, oben rechts, unten links) eines Rechtecks auf der Wand. */
const wandFlaeche = (x: number, y: number, w: number, h: number) =>
  [aufWand(x, y), aufWand(x + w, y), aufWand(x, y + h)] as const

/** Kontingent: breit, die beiden Zeitfenster nebeneinander. */
export const KONTINGENT_MASS = { w: 660, h: 170 }
export const WAND_KONTINGENT = wandFlaeche(0, 0, KONTINGENT_MASS.w, KONTINGENT_MASS.h)

/** Binäruhr: mittig über dem Kontingent. */
export const BINAER_MASS = { w: 364, h: 238 }
export const WAND_BINAER = wandFlaeche(
  (KONTINGENT_MASS.w - BINAER_MASS.w) / 2,
  -BINAER_MASS.h - 58,
  BINAER_MASS.w,
  BINAER_MASS.h,
)
/** Die Binäruhr als Viereck (oben links, oben rechts, unten rechts, unten links), Pixel. */
const BINAER_ECKEN = (() => {
  const [ol, or, ul] = WAND_BINAER
  const ur: Punkt = [or[0] + ul[0] - ol[0], or[1] + ul[1] - ol[1]]
  return [ol, or, ur, ul] as const
})()
/** Rechteck um die Binäruhr in Prozent der Bühne. */
const BINAER_FLAECHE: Rechteck = (() => {
  const xs = BINAER_ECKEN.map((p) => p[0])
  const ys = BINAER_ECKEN.map((p) => p[1])
  const l = Math.min(...xs)
  const t = Math.min(...ys)
  return {
    l: (l / 2048) * 100,
    t: (t / 1152) * 100,
    w: ((Math.max(...xs) - l) / 2048) * 100,
    h: ((Math.max(...ys) - t) / 1152) * 100,
  }
})()
/** Form der Binäruhr in Prozent ihres Rechtecks (Maske beim Scharfstellen). */
const BINAER_FORM = BINAER_ECKEN.map(
  ([x, y]) =>
    [
      ((x / 2048) * 100 - BINAER_FLAECHE.l) / (BINAER_FLAECHE.w / 100),
      ((y / 1152) * 100 - BINAER_FLAECHE.t) / (BINAER_FLAECHE.h / 100),
    ] as const,
)
/** Mitte der Binäruhr (Prozent), für die Kamera. */
const BINAER_MITTE: Punkt = [
  BINAER_FLAECHE.l + BINAER_FLAECHE.w / 2,
  BINAER_FLAECHE.t + BINAER_FLAECHE.h / 2,
]

// Reihenfolge = Stapelung: spätere liegen oben (Werkzeugwand über Werkbank).
export const STATIONEN: Station[] = [
  // Team-Modus: der Büroboden zwischen den Schreibtischen. Ganz unten, damit die
  // Sitze (eigene Knöpfe) und die Wandobjekte davor Vorrang haben.
  {
    id: 'firma',
    l: 27,
    t: 9,
    w: 40,
    h: 26,
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
  // Der breite Bildschirm auf der Werkbank: steht vor der Lochwand. Klickbar ist
  // nur seine echte Form (`form`), nicht das Rechteck drumherum.
  {
    id: 'monitore',
    l: 76.221,
    t: 38.108,
    w: 12.939,
    h: 20.573,
    label: 'Chat-Ansicht',
    hint: 'Durch den Monitor in den vollen Chat',
    panel: 'chat',
    form: [
      [4.336, 1.687],
      [98.51, 56.75],
      [92.64, 98.43],
      [1.507, 37.55],
    ],
  },
  {
    id: 'uhr',
    ...BINAER_FLAECHE,
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
  // Postkorb am rechten Ende der Werkbank: liegt über ihr, darum danach.
  {
    id: 'postfach',
    l: 87.8,
    t: 57.4,
    w: 5.2,
    h: 7.4,
    label: 'E-Mails',
    hint: 'Posteingang',
    panel: 'mail',
  },
  // Karteikasten auf seinem Schränkchen links neben der Werkbank.
  {
    id: 'tafel',
    l: 59.497,
    t: 41.319,
    w: 6.982,
    h: 17.361,
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
  monitore: { l: 76.221, t: 38.108, w: 12.939, h: 20.573 },
  werkbank: { l: 68.848, t: 35.069, w: 28.906, h: 46.701 }, // mit Monitor + Tastatur
  werkzeug: { l: 79.102, t: 25.434, w: 13.574, h: 26.302 },
  uhr: BINAER_FLAECHE, // ohne Bild: siehe VIELECK
  kalender: { l: 91.113, t: 32.378, w: 8.008, h: 19.271 },
  steckfeld: { l: 93.408, t: 48.698, w: 6.592, h: 16.233 },
  postfach: { l: 88.054, t: 58.474, w: 4.361, h: 5.589 },
  pult: { l: 47.412, t: 47.83, w: 5.566, h: 26.823 },
  tafel: { l: 59.497, t: 41.319, w: 6.982, h: 17.361 },
  firma: { l: 27, t: 9, w: 40, h: 26 },
}

/** Was nicht im Raumbild gemalt ist, hat statt einer Bildmaske ein Vieleck
 *  (Prozent seiner FORM-Fläche). */
export const VIELECK: Partial<Record<StationId, readonly Punkt[]>> = { uhr: BINAER_FORM }

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

/** Der Karteikasten der Tickets samt Schatten (Ebene, Prozent der Bühne).
 *  Steht links neben der Werkbank, etwas nach hinten versetzt: dort, wo man an
 *  der Werkbank arbeitet, verdeckt man ihn nicht. Gebaut mit
 *  construct-raum-art/team/kasten.py 1290 676 200. */
export const KASTEN: Rechteck = { l: 58.032, t: 38.715, w: 9.912, h: 22.569 }

/** Der Postkorb der E-Mails samt Schatten (Ebene) am rechten Ende der Werkbank.
 *  Gebaut mit construct-raum-art/team/postkorb.py 1848 738 0.58. */
export const POSTKORB: Rechteck = { l: 87.657, t: 57.769, w: 5.154, h: 6.998 }

/** Der Bildschirm auf der Werkbank: Fläche, auf der der Terminal-Text liegt (oben links,
 *  oben rechts, unten rechts, unten links; Prozent). Die genaue Form gibt
 *  assets/fernseher-maske.webp vor. */
export const FERNSEHER: readonly [Punkt, Punkt, Punkt, Punkt] = [
  [76.782, 38.455],
  [88.967, 49.783],
  [88.208, 58.359],
  [76.416, 45.833],
]
/** Größe der Terminalfläche: so groß, wie sie bei diesem Zoom auf dem
 *  Bildschirm wäre — der Text bleibt beim Hineinfahren scharf. */
export const FERNSEHER_ZOOM = 5.4

/** Kamera „durch den Monitor“: so nah, dass der Bildschirm alles füllt. */
export const EINTAUCHEN: Kamera = { z: 12, f: [82.6, 48.1], p: [50, 50] }

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
  uhr: { z: 2.2, f: BINAER_MITTE, p: [80, 40], seite: 'links', breite: 50, ziel: BINAER_MITTE },
  mcp: { z: 1.8, f: [96.9, 56.8], p: [84, 52], seite: 'links', breite: 38, ziel: [96.9, 56.8] },
  mail: { z: 1.6, f: [90.2, 61.3], p: [82, 56], seite: 'links', breite: 62, ziel: [90.2, 61.3] },
  ausruestung: { z: 1.35, f: [48, 52], p: [26, 55], seite: 'rechts', breite: 46, ziel: [50.2, 58] },
  tickets: { z: 1.5, f: [63, 50], p: [76, 52], seite: 'links', breite: 54, ziel: [63, 50] },
  personal: { z: 1.6, f: [47, 24], p: [22, 50], seite: 'rechts', breite: 62, ziel: [47, 24] },
  auftraege: { z: 1.6, f: [47, 24], p: [24, 50], seite: 'rechts', breite: 56, ziel: [47, 24] },
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

/** Die Doppelschreibtische stehen im freien Hinterraum, links und rechts von der
 *  Figur auf dem Podest (deren Kopf reicht bis knapp unter ihre Vorderkante).
 *  Zwei Leute sitzen sich gegenüber: einer links, einer rechts. Fußpunkt = Mitte der
 *  Vorderkante. */
export const PAARE: Record<PaarId, Platz> = {
  a: { x: 760, y: 392, s: 1.2 },
  b: { x: 1170, y: 388, s: 1.2 },
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

/** Bilder des Büros (mitgeliefert). */
export const BUERO_SPRITES = '/static/team/raum'

/** Wo ein Tischbild auf der Bühne liegt (Prozent). */
export function tischFlaeche(p: Platz): Rechteck {
  const k = (DOPPEL_HOEHE / DOPPEL.inhaltH) * p.s
  const w = DOPPEL.w * k
  const h = DOPPEL.h * k
  return {
    l: ((p.x - w / 2) / BUERO_BUEHNE.w) * 100,
    t: ((p.y + DOPPEL.rand * k - h) / BUERO_BUEHNE.h) * 100,
    w: (w / BUERO_BUEHNE.w) * 100,
    h: (h / BUERO_BUEHNE.h) * 100,
  }
}

/** Die Schreibtische samt Leuten als Form fürs Scharfstellen: beim Überfahren
 *  des Büros bleiben sie scharf, der Rest des Raums wird unscharf. */
export const BUERO_FORM = (Object.keys(PAARE) as PaarId[]).map((id) => ({
  bild: `${BUERO_SPRITES}/doppel-${id}-beide.webp`,
  flaeche: tischFlaeche(PAARE[id]),
}))

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
  { x: 1440, y: 372, s: 1 },
  { x: 1510, y: 380, s: 1 },
]

/** Wo an der Werkbank die Füße stehen (Pixel auf dem Raumbild): dort läuft ein
 *  Mitarbeiter hin, wenn er arbeitet. */
export const WERKBANK_FUSS = { x: 1470, y: 892 }
