import { create } from 'zustand'

// Auf- und zugeklappte Projekte der Skill-Liste. Überlebt den Wechsel in andere
// Ansichten (früher openFolders['sk:…']), aber kein Neuladen der Seite.
interface SkillsState {
  closed: Record<string, boolean>
  toggle: (proj: string) => void
}

export const useSkillsUi = create<SkillsState>((set) => ({
  closed: {},
  toggle: (proj) => set((s) => ({ closed: { ...s.closed, [proj]: !s.closed[proj] } })),
}))
