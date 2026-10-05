import { createContext, useContext } from 'react'
import type { AgentInfo } from '@/stores/chat'

/** Mit wem das offene Gespräch geführt wird: ein Mitarbeiter der Firma, sonst null
 *  (der Assistent). Die Nachrichten übernehmen davon Name und Bild. */
export const AgentKontext = createContext<AgentInfo | null>(null)
export const useAgentKontext = () => useContext(AgentKontext)
