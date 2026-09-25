import { useEffect, useState } from 'react'

// Eigenes Hintergrundbild fürs Plasma-Glas: das Glas liest rohe Pixel, die
// CSS-Abdunkelung des normalen Hintergrunds gilt dort nicht. Darum wird das
// Bild hier einmal in einen Canvas gemalt und dort abgedunkelt — sonst wäre
// Schrift auf einem hellen Foto unlesbar.
const MAX = 2400

export function useDimmedImage(url: string, dim: number): HTMLCanvasElement | null {
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null)
  useEffect(() => {
    if (!url) return
    let alive = true
    const img = new Image()
    img.onload = () => {
      if (!alive) return
      const k = Math.min(1, MAX / Math.max(img.naturalWidth, img.naturalHeight))
      const c = document.createElement('canvas')
      c.width = Math.round(img.naturalWidth * k)
      c.height = Math.round(img.naturalHeight * k)
      const cx = c.getContext('2d')
      if (!cx) return
      cx.drawImage(img, 0, 0, c.width, c.height)
      cx.fillStyle = `rgba(0,0,0,${Math.max(0, Math.min(100, dim)) / 100})`
      cx.fillRect(0, 0, c.width, c.height)
      setCanvas(c)
    }
    img.src = url
    return () => {
      alive = false
    }
  }, [url, dim])
  return url ? canvas : null
}
