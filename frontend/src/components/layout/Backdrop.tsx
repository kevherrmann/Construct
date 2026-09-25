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

interface RainProps {
  slow: boolean
  /** Als Bildquelle fürs Plasma-Glas: unsichtbar, Zeichen gedämpft (die CSS-
   *  Deckkraft von 28 % gilt dort nicht — das Glas liest die rohen Pixel). */
  source?: boolean
  /** Nicht zeichnen (Canvas bleibt bestehen) — spart Rechenzeit. */
  paused?: boolean
  onCanvas?: (c: HTMLCanvasElement | null) => void
}

export function MatrixRain({ slow, source, paused, onCanvas }: RainProps) {
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
      // Plasma-Glas lädt Quellen mit UNPACK_FLIP_Y und dreht sie dabei
      // senkrecht um — als Quelle darum gespiegelt zeichnen, dann steht der
      // Regen wieder richtig (fällt von oben, Zeichen aufrecht). Neues Maß
      // setzt die Transformation zurück, darum hier bei jedem Größenwechsel.
      if (source) cx.setTransform(1, 0, 0, -1, 0, cv.height)
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
      if (paused) return
      if (t - last < every) return
      last = t
      const { color, fade } = colors.current
      cx.globalAlpha = 1
      cx.fillStyle = fade
      cx.fillRect(0, 0, cv.width, cv.height)
      cx.fillStyle = color
      cx.globalAlpha = source ? 0.55 : 1
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
  }, [slow, source, paused])

  useEffect(() => {
    onCanvas?.(ref.current)
    return () => onCanvas?.(null)
  }, [onCanvas])

  return <canvas ref={ref} className={source ? s.source : s.rain} />
}

// Hintergrund: Matrix-Regen (Vorgabe), eigenes Bild, schlicht — und mit
// Plasma das bewegte Plasma-Feld. Mit echtem Plasma (WebGL) malt PlasmaRoot
// den Hintergrund selbst durchs Glas; hier bleibt dann nichts zu tun.
export function Backdrop() {
  const bg = useSettings((st) => st.settings.background)
  const plasma = useSettings((st) => st.settings.plasma)
  const fx = fxLevel()
  if (plasmaLive(plasma)) return null
  // Das Plasma-Feld gibt es nur mit WebGL — sonst gilt die Wahl als Regen.
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
  if ((bg.mode === 'matrix' || bg.mode === 'plasma') && fx !== 'off')
    return <MatrixRain slow={fx === 'low'} />
  return null
}
