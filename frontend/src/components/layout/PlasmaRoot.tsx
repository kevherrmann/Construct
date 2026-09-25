import { useEffect, type ReactNode } from 'react'
import { PlasmaProvider } from '@cruxgarden/plasma-ui'
import { plasmaLive } from '@/lib/plasma'
import { useSettings } from '@/stores/settings'
import { PlasmaActive } from './plasmaContext'

// Plasma-Theme: ein Vollbild-Canvas hinter der App malt das Farbfeld und die
// Glas-Flächen (Surface). Nur geladen, wenn das Theme gewählt ist und die
// Grafik es hergibt — sonst bleibt alles beim Alten.
export function PlasmaRoot({ children }: { children: ReactNode }) {
  const theme = useSettings((st) => st.settings.theme)
  const bg = useSettings((st) => st.settings.background)
  const live = plasmaLive(theme)

  useEffect(() => {
    // Für die CSS: echte Flächen vom Canvas, oder die Glas-Optik als Ersatz.
    document.documentElement.classList.toggle('plasma-gl', live)
  }, [live])

  if (!live) return <PlasmaActive.Provider value={false}>{children}</PlasmaActive.Provider>
  return (
    <PlasmaProvider
      mood="tidal"
      theme="dark"
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
