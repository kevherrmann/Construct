import type { CSSProperties } from 'react'
import { uploadFile } from '@/api/settings'
import { trServer } from '@/lib/serverText'

/** Bild hochladen und die URL liefern; Fehler als alert wie früher. */
export async function pickUpload(file: File | undefined, failed: string) {
  if (!file) return null
  try {
    const j = await uploadFile(file)
    if (j.url) return j.url
    window.alert(failed)
  } catch (e) {
    window.alert(trServer((e as Error).message) || failed)
  }
  return null
}

/** Vorschau: das Bild so abgedunkelt, wie es hinter der Oberfläche läge. */
export function previewStyle(bg: { image: string }, dim: number): CSSProperties {
  if (!bg.image) return { backgroundImage: 'none' }
  const a = (dim / 100).toFixed(2)
  return {
    backgroundImage: `linear-gradient(rgba(0,0,0,${a}),rgba(0,0,0,${a})), url("${bg.image}")`,
  }
}
