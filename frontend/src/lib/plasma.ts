import { fxLevel } from './fx'

// Plasma zeichnet seine Flächen per WebGL2 in einen Vollbild-Canvas. Ohne
// WebGL2 (ältere WebKitGTK, Software-Rendering) oder im Sparmodus gibt es
// stattdessen die CSS-Glas-Optik aus styles/plasma.css — gleiche Anordnung,
// kein Shader.
let gl: boolean | null = null
export function webgl2(): boolean {
  if (gl !== null) return gl
  try {
    gl = !!document.createElement('canvas').getContext('webgl2')
  } catch {
    gl = false
  }
  return gl
}

/** Echtes Plasma: Theme gewählt, WebGL2 da, volle Optik erlaubt. */
export const plasmaLive = (theme: string) => theme === 'plasma' && fxLevel() === 'full' && webgl2()
