import { useSyncExternalStore } from 'react'
import { getItem, setItem } from './storage'

// Sparmodus. Ohne GPU-Beschleunigung ist der Vollbild-Canvas auf einem
// 4K-Schirm der mit Abstand teuerste Teil der Oberfläche — er kostet dann mehr
// als die halbe CPU eines Kerns und verzögert sichtbar die Texteingabe.
// Mit ?fx=low in der Adresse (z.B. ein Browser ohne GPU) oder selbst
// übersteuern (Browser-Konsole):
//   localStorage.setItem('mxfx','full')  → volle Optik, mehr Last
//   localStorage.setItem('mxfx','low')   → sparsam, auch im Browser
//   localStorage.setItem('mxfx','off')   → Regen ganz aus, der Raum steht still
//   localStorage.removeItem('mxfx')      → wieder automatisch
// „Effekte aus“ in ⚙ → Aussehen setzt 'off' bzw. nimmt es wieder weg.
export type FxLevel = 'full' | 'low' | 'off'

// ?fx=low beim Laden festhalten: der Router leitet / sofort auf /chat um und
// wirft die Query dabei weg. Später gelesen, lief sonst doch die volle Optik.
const urlLow = new URLSearchParams(location.search).get('fx') === 'low'

export function fxLevel(): FxLevel {
  const pref = getItem('mxfx')
  if (pref === 'off') return 'off'
  if (pref === 'low') return 'low'
  if (pref !== 'full' && urlLow) return 'low'
  return 'full'
}

const hoerer = new Set<() => void>()

/** Klassen am body, an denen das CSS hängt (Unschärfe, Atmen der Figur, Wege). */
export function applyFx() {
  const fx = fxLevel()
  document.body.classList.toggle('fx-off', fx === 'off')
  document.body.classList.toggle('fx-low', fx === 'low')
}

/** Effekte aus- oder wieder einschalten, wirkt sofort und bleibt gemerkt. */
export function setEffekteAus(aus: boolean) {
  setItem('mxfx', aus ? 'off' : null)
  applyFx()
  hoerer.forEach((h) => h())
}

/** fxLevel() als Hook: Videos und Regen folgen dem Schalter ohne Neuladen. */
export function useFx(): FxLevel {
  return useSyncExternalStore(
    (h) => {
      hoerer.add(h)
      return () => hoerer.delete(h)
    },
    fxLevel,
    fxLevel,
  )
}
