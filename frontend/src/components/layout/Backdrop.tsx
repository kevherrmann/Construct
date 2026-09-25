import { useEffect, useRef, type CSSProperties } from 'react'
import { fxLevel } from '@/lib/fx'
import { plasmaLive } from '@/lib/plasma'
import { useSettings } from '@/stores/settings'
import s from './Backdrop.module.css'

// Der Regen ist Deko bei 28 % Deckkraft hinter allem und muss nicht in voller
// Auflösung rastern: auf 4K wären das 8,3 Mio. Pixel pro Frame. Bei halber
// Auflösung ist es ein Viertel davon; hochskaliert sieht man es nicht.
const RAIN_SCALE = 0.5
const CELL = 14
const GLYPHS = 'ｱｲｳｴｵｶｷｸ0123456789ABCDEFﾊﾋﾌﾍﾎ$+*=<>'

function MatrixRain({ slow }: { slow: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const theme = useSettings((st) => st.settings.theme)
  // Canvas versteht keine CSS-Variablen: einmal pro Theme auslesen, nicht pro
  // Frame (das erzwänge ständiges Neu-Berechnen des Stils). Der Regen selbst
  // läuft beim Themenwechsel einfach weiter, nur in neuer Farbe.
  const colors = useRef({ color: '#00ff41', fade: 'rgba(0,6,0,.07)' })
  useEffect(() => {
    const cs = getComputedStyle(document.documentElement)
    colors.current = {
      color: cs.getPropertyValue('--rain').trim() || '#00ff41',
      fade: cs.getPropertyValue('--rain-fade').trim() || 'rgba(0,6,0,.07)',
    }
  }, [theme])

  useEffect(() => {
    const cv = ref.current
    const cx = cv?.getContext('2d')
    if (!cv || !cx) return
    let step = CELL * RAIN_SCALE
    let drops: number[] = []
    const size = () => {
      cv.width = Math.max(1, Math.round(innerWidth * RAIN_SCALE))
      cv.height = Math.max(1, Math.round(innerHeight * RAIN_SCALE))
      step = CELL * RAIN_SCALE
      drops = Array<number>(Math.floor(cv.width / step)).fill(1)
    }
    size()
    addEventListener('resize', size)
    // Bildrate — der wirksamste Regler für die CPU-Last, weil jeder Frame ein
    // Neu-Zusammensetzen aller Ebenen darüber auslöst. Gemessen auf 4K ohne
    // GPU: 55 ms = 33 % CPU, 110 ms = 21 %, Regen aus = 3,7 %.
    const every = slow ? 110 : 55
    let last = 0
    let raf = 0
    // requestAnimationFrame statt setInterval: pausiert von selbst, wenn das
    // Fenster unsichtbar ist, und staut nie Frames auf.
    const loop = (t: number) => {
      raf = requestAnimationFrame(loop)
      if (t - last < every) return
      last = t
      const { color, fade } = colors.current
      cx.fillStyle = fade
      cx.fillRect(0, 0, cv.width, cv.height)
      cx.fillStyle = color
      cx.font = `${step}px monospace`
      for (let i = 0; i < drops.length; i++) {
        cx.fillText(GLYPHS[Math.floor(Math.random() * GLYPHS.length)]!, i * step, drops[i]! * step)
        if (drops[i]! * step > cv.height && Math.random() > 0.975) drops[i] = 0
        drops[i]!++
      }
    }
    raf = requestAnimationFrame(loop)
    return () => {
      cancelAnimationFrame(raf)
      removeEventListener('resize', size)
    }
  }, [slow])

  return <canvas ref={ref} className={s.rain} />
}

// Hintergrund: Matrix-Regen (Vorgabe), eigenes Bild oder schlicht.
export function Backdrop() {
  const bg = useSettings((st) => st.settings.background)
  const plasma = useSettings((st) => st.settings.plasma)
  const fx = fxLevel()
  const image = bg.mode === 'image' && !!bg.image
  // Plasma malt sein Feld selbst (und bricht ein eigenes Bild durchs Glas);
  // ohne WebGL steht ein ruhiger Verlauf in den Theme-Farben da.
  if (plasma && plasmaLive(plasma)) return null
  if (plasma && !image) return <div className={s.plasmaField} />
  if (bg.mode === 'image' && bg.image)
    return (
      <div
        className={s.image}
        style={
          {
            backgroundImage: `url("${bg.image}")`,
            '--bg-dim': ((bg.dim ?? 60) / 100).toFixed(2),
          } as CSSProperties
        }
      />
    )
  if (bg.mode === 'matrix' && fx !== 'off') return <MatrixRain slow={fx === 'low'} />
  return null
}
