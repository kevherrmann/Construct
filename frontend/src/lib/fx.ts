import { getItem } from './storage'

// Sparmodus. Ohne GPU-Beschleunigung ist der Vollbild-Canvas auf einem
// 4K-Schirm der mit Abstand teuerste Teil der Oberfläche — er kostet dann mehr
// als die halbe CPU eines Kerns und verzögert sichtbar die Texteingabe.
// desktop.py hängt ?fx=low an, wenn es auf Software-Rendering ausweichen
// musste. Selbst übersteuern (Browser-Konsole):
//   localStorage.setItem('mxfx','full')  → volle Optik, mehr Last
//   localStorage.setItem('mxfx','low')   → sparsam, auch im Browser
//   localStorage.setItem('mxfx','off')   → Regen ganz aus
//   localStorage.removeItem('mxfx')      → wieder automatisch
export type FxLevel = 'full' | 'low' | 'off'

export function fxLevel(): FxLevel {
  const pref = getItem('mxfx')
  if (pref === 'off') return 'off'
  if (pref === 'low') return 'low'
  if (pref !== 'full' && new URLSearchParams(location.search).get('fx') === 'low') return 'low'
  return 'full'
}
