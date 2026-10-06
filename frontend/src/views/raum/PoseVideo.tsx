import { useEffect, useRef, useState } from 'react'
import { RUHIG, useMedien } from '@/hooks/useMedien'
import type { Rechteck } from './stationen'
import s from './Raum.module.css'

/** Kurze Schleife einer Pose. Erstes und letztes Bild = Standbild der Pose,
 *  die Maske (Figur mit Rand) lässt drumherum den Raum durch. */
export interface Clip {
  webm: string
  mp4: string
  maske: string
}

/** Schleife einer Pose. Startet beim Einblenden vorn, damit das erste Bild
 *  genau auf dem Standbild liegt — die Überblendung springt dann nicht.
 *  Bei „Bewegung reduzieren“ spielt sie nie: dann bleibt das Standbild stehen. */
export function PoseVideo({
  clip,
  ort,
  an,
  onLaeuft,
}: {
  clip: Clip
  ort: Rechteck
  an: boolean
  onLaeuft?: (v: boolean) => void
}) {
  const ref = useRef<HTMLVideoElement>(null)
  const [laeuft, setLaeuft] = useState(false)
  const ruhig = useMedien(RUHIG)
  const spielt = an && !ruhig
  useEffect(() => {
    const v = ref.current
    if (!v) return
    if (ruhig) {
      v.pause()
      return
    }
    if (an) {
      v.currentTime = 0
      v.play().catch(() => {}) // Autoplay verweigert: dann bleibt das Standbild
    } else {
      const id = setTimeout(() => v.pause(), 500) // erst nach der Ausblendung
      return () => clearTimeout(id)
    }
  }, [an, ruhig])
  const melde = (v: boolean) => {
    setLaeuft(v)
    onLaeuft?.(v)
  }
  return (
    <video
      ref={ref}
      className={`${s.video} ${spielt && laeuft ? s.videoAn : ''}`}
      style={{
        left: `${ort.l}%`,
        top: `${ort.t}%`,
        width: `${ort.w}%`,
        height: `${ort.h}%`,
        maskImage: `url(${clip.maske})`,
        WebkitMaskImage: `url(${clip.maske})`,
      }}
      muted
      loop
      playsInline
      preload="auto"
      aria-hidden
      onPlaying={() => melde(true)}
      onPause={() => melde(false)}
      onError={() => melde(false)}
    >
      <source src={clip.webm} type="video/webm" />
      <source src={clip.mp4} type="video/mp4" />
    </video>
  )
}
