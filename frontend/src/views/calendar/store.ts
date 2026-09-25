import { create } from 'zustand'
import { todayYMD } from './dates'

// Welcher Monat und Tag gerade offen sind. Bleibt beim Wechsel in andere
// Ansichten erhalten — wie in der alten Oberfläche, wo das globale Variablen waren.
interface CalendarState {
  year: number
  /** 0-basiert. */
  month: number
  /** Ausgewählter Tag (YYYY-MM-DD) oder null = kein Tages-Detail. */
  sel: string | null
  /** Einmalig: Titelfeld im Tages-Detail fokussieren ("＋ TERMIN"). */
  focusAdd: boolean
  prev: () => void
  next: () => void
  /** Zum heutigen Tag springen und ihn auswählen. */
  today: () => void
  /** Tag auswählen und dessen Monat zeigen. */
  jump: (ds: string) => void
  select: (ds: string) => void
  /** Heute öffnen und das Eingabefeld fokussieren. */
  openAdd: () => void
  focusDone: () => void
}

const now = new Date()

export const useCalendar = create<CalendarState>((set) => ({
  year: now.getFullYear(),
  month: now.getMonth(),
  sel: null,
  focusAdd: false,
  prev: () =>
    set((s) => (s.month === 0 ? { month: 11, year: s.year - 1 } : { month: s.month - 1 })),
  next: () =>
    set((s) => (s.month === 11 ? { month: 0, year: s.year + 1 } : { month: s.month + 1 })),
  today: () => {
    const n = new Date()
    set({ year: n.getFullYear(), month: n.getMonth(), sel: todayYMD() })
  },
  jump: (ds) => {
    const [y, m] = ds.split('-').map(Number)
    set({ year: y!, month: m! - 1, sel: ds })
  },
  select: (ds) => set({ sel: ds }),
  openAdd: () => {
    const n = new Date()
    set({ year: n.getFullYear(), month: n.getMonth(), sel: todayYMD(), focusAdd: true })
  },
  focusDone: () => set({ focusAdd: false }),
}))
