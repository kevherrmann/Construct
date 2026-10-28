/** Nach so langer Zeit ohne Maus oder Tastatur sieht vermutlich keiner hin. */
export const RUHE_MS = 3 * 60_000

// Ein gemeinsamer Zustand für alle, die fragen: Regen, Raum-Video, Tippgeräusch.
// Verborgen erkennt der Browser selbst (anderer Tab, minimiert). Ein Fenster,
// das nur von anderen verdeckt ist, meldet unter Linux niemand — darum zählt
// auch, ob seit RUHE_MS jemand Maus oder Tastatur benutzt hat.
let ruht = false
let letzte = Date.now()
let uhr: ReturnType<typeof setInterval> | undefined
const hoerer = new Set<() => void>()

const melden = () => hoerer.forEach((h) => h())

function pruefen() {
  const jetzt = document.hidden || Date.now() - letzte > RUHE_MS
  if (jetzt !== ruht) {
    ruht = jetzt
    melden()
  }
}

function eingabe() {
  letzte = Date.now()
  if (ruht) pruefen()
}

const EINGABEN = ['pointermove', 'pointerdown', 'keydown', 'wheel', 'focus'] as const

export function abonnieren(h: () => void) {
  hoerer.add(h)
  if (hoerer.size === 1) {
    for (const e of EINGABEN) addEventListener(e, eingabe, { passive: true, capture: true })
    document.addEventListener('visibilitychange', pruefen)
    uhr = setInterval(pruefen, 15_000)
    letzte = Date.now()
    pruefen()
  }
  return () => {
    hoerer.delete(h)
    if (hoerer.size) return
    for (const e of EINGABEN) removeEventListener(e, eingabe, { capture: true })
    document.removeEventListener('visibilitychange', pruefen)
    clearInterval(uhr)
  }
}

/** Sieht gerade keiner hin? Für Töne, die außerhalb einer Komponente geplant werden. */
export const ruhtGerade = () => ruht || document.hidden

export const ruhtJetzt = () => ruht
