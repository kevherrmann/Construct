import { createContext } from 'react'

/** ID der Antwort, in der ein Baustein (GenUi.tsx) steht — damit Antwort-Buttons
 *  wissen, ob schon jemand darauf geantwortet hat. */
export const AntwortId = createContext<string | null>(null)
