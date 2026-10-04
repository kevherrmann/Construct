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

// Reihenfolge = Stapelung: spätere liegen oben (Werkzeugwand über Werkbank).
export const STATIONEN: Station[] = [
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

/** Wo die Figur steht: Fußpunkt (Mitte unten) und Höhe, in Prozent der Bühne. */
export const FIGUR = { x: 45.65, y: 75.7, h: 40.8 }

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
export const PODEST_VIDEO: Rechteck = { l: 31.982, t: 26.042, w: 27.344, h: 60.764 }
export const WERKBANK: Rechteck = { l: 54.688, t: 23.09, w: 37.5, h: 72.222 }

/** Kontingent-Anzeige an der Wand links neben der Uhr, über der Lochwand
 *  (Pixel im Raumbild: oben links, oben rechts, unten links). Oberkante im
 *  Winkel der Wand wie die Lochwand, die Senkrechte kippt wie bei der Uhr. */
export const WAND_KONTINGENT: readonly [Punkt, Punkt, Punkt] = [
  [1650, 140],
  [1846, 211],
  [1647, 296],
]

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
