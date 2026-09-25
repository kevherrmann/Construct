import { useEffect, useState, type ReactNode } from 'react'
import { PlasmaProvider, resolveMood, type Mood } from '@cruxgarden/plasma-ui'
import { plasmaLive } from '@/lib/plasma'
import { THEMES } from '@/lib/themes'
import { useDimmedImage } from '@/hooks/useDimmedImage'
import { MatrixRain } from './Backdrop'
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

  // Was hinter dem Glas liegt — die Wahl unter ⚙ → Hintergrund:
  //   plasma  das bewegte Feld der Stimmung (prozedural, kein Bild)
  //   matrix  der laufende Regen, live durchs Glas gebrochen
  //   image   das eigene Bild, abgedunkelt
  //   plain   ruhiger Grund in der Theme-Farbe
  const [rain, setRain] = useState<HTMLCanvasElement | null>(null)
  const photo = useDimmedImage(bg.mode === 'image' ? bg.image : '', bg.dim ?? 60)
  const background =
    bg.mode === 'plasma'
      ? undefined
      : bg.mode === 'matrix'
        ? (rain ?? base)
        : bg.mode === 'image' && bg.image
          ? (photo ?? base)
          : base

  useEffect(() => {
    // Für die CSS: echte Flächen vom Canvas, oder die Glas-Optik als Ersatz.
    document.documentElement.classList.toggle('plasma-gl', live)
  }, [live])

  if (!live) return <PlasmaActive.Provider value={false}>{children}</PlasmaActive.Provider>
  return (
    <PlasmaProvider
      mood={mood}
      theme={info.light ? 'light' : 'dark'}
      background={background}
      // Lesbarkeit vor Effekt: leicht mattiert, kaum getönt. Ein Foto ist
      // unruhiger als das Feld — dort tönt das Glas kräftig in der Grundfarbe
      // des Themes, sonst wird die Schrift auf milchigem Grau zu schwach.
      tint={base}
      frost={0.35}
      opacity={bg.mode === 'image' ? 0.55 : 0.06}
      elevation={0.3}
      // Kein Tropfen, der dem Mauszeiger folgt — lenkt beim Lesen ab.
      pointerDrop={false}
      grain={0.6}
    >
      {/* Bleibt bestehen, solange Plasma läuft, und pausiert, wenn ein anderer
          Hintergrund gewählt ist: so wechselt das Glas beim Umschalten direkt
          auf den Canvas. Kam er erst mit dem Umschalten dazu (Farbe → Canvas),
          blieb der Regen hinter dem Glas unsichtbar. */}
      <MatrixRain slow={false} source paused={bg.mode !== 'matrix'} onCanvas={setRain} />
      <PlasmaActive.Provider value>{children}</PlasmaActive.Provider>
    </PlasmaProvider>
  )
}
