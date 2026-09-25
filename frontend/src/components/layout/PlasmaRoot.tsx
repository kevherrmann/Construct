import { useEffect, type ReactNode } from 'react'
import { PlasmaProvider, resolveMood, type Mood } from '@cruxgarden/plasma-ui'
import { plasmaLive } from '@/lib/plasma'
import { THEMES } from '@/lib/themes'
import { useSettings } from '@/stores/settings'
import { PlasmaActive } from './plasmaContext'

// Plasma: ein Vollbild-Canvas hinter der App malt das Farbfeld und die
// Glas-Flächen (Surface). Nur aktiv, wenn der Schalter an ist und die
// Grafik es hergibt — sonst bleibt alles beim Alten.
export function PlasmaRoot({ children }: { children: ReactNode }) {
  const theme = useSettings((st) => st.settings.theme)
  const on = useSettings((st) => st.settings.plasma)
  const bg = useSettings((st) => st.settings.background)
  const live = plasmaLive(on)
  // Das Farbfeld in den Farben der gewählten Farbwelt: Grund, gedämpfter
  // Mittelton, Akzent. Federung und Verschmelzen wie bei "tidal".
  const info = THEMES.find((x) => x.key === theme) ?? THEMES[0]!
  const [base, accent, faint] = info.swatch
  const mood: Mood = { ...resolveMood('tidal'), colors: [base, faint, accent] }

  useEffect(() => {
    // Für die CSS: echte Flächen vom Canvas, oder die Glas-Optik als Ersatz.
    document.documentElement.classList.toggle('plasma-gl', live)
  }, [live])

  if (!live) return <PlasmaActive.Provider value={false}>{children}</PlasmaActive.Provider>
  return (
    <PlasmaProvider
      mood={mood}
      theme={info.light ? 'light' : 'dark'}
      // Eigenes Hintergrundbild wird durch das Glas gebrochen; sonst das
      // prozedurale Farbfeld der Stimmung.
      background={bg.mode === 'image' && bg.image ? bg.image : undefined}
      // Lesbarkeit vor Effekt: leicht mattiert, kaum getönt.
      frost={0.35}
      opacity={0.06}
      elevation={0.3}
      // Kein Tropfen, der dem Mauszeiger folgt — lenkt beim Lesen ab.
      pointerDrop={false}
      grain={0.6}
    >
      <PlasmaActive.Provider value>{children}</PlasmaActive.Provider>
    </PlasmaProvider>
  )
}
