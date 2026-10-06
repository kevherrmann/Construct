import { create } from 'zustand'

// Welcher Auftrag offen ist und was man darin ansieht. Bleibt beim Wechsel in
// andere Ansichten erhalten.
interface AuftraegeState {
  /** Auftrags-ID, 'neu' (Formular) oder null (nichts gewählt). */
  auswahl: string | 'neu' | null
  /** 'uebersicht' (Besetzung + Ergebnis), 'verlauf' (alle Nachrichten) oder der Slug einer Person. */
  sicht: string
  /** Was das Protokoll im Raum zeigt: den Verlauf dieses Auftrags, bei null den Chat
   *  der offenen Session. Es gilt, was du zuletzt gewählt hast: einen Auftrag öffnen
   *  setzt ihn, eine Session öffnen (stores/chat) setzt ihn zurück. */
  protokoll: string | null
  oeffne: (id: string) => void
  /** Wählt den Auftrag aus, ohne dass das Protokoll zu ihm wechselt — für Aufträge,
   *  die nicht du geöffnet hast (/firma legt einen an, du redest weiter im Chat). */
  vormerken: (id: string) => void
  zurSession: () => void
  neu: () => void
  sichtWechseln: (sicht: string) => void
  schliessen: () => void
}

export const useAuftraegeAnsicht = create<AuftraegeState>((set) => ({
  auswahl: null,
  sicht: 'uebersicht',
  protokoll: null,
  oeffne: (id) => set({ auswahl: id, sicht: 'uebersicht', protokoll: id }),
  vormerken: (id) => set({ auswahl: id, sicht: 'uebersicht' }),
  zurSession: () => set({ protokoll: null }),
  neu: () => set({ auswahl: 'neu' }),
  sichtWechseln: (sicht) => set({ sicht }),
  schliessen: () => set({ auswahl: null, sicht: 'uebersicht' }),
}))
