import { createContext } from 'react'

/** Läuft gerade echtes Plasma (WebGL)? Gesetzt von PlasmaRoot, gelesen von Surface. */
export const PlasmaActive = createContext(false)
