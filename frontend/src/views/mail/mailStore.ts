import { create } from 'zustand'
import type { MailSummary } from '@/api/mail'

// Reiner Oberflächenzustand der Mail-Ansicht: Filter, Auswahl, Entwurf. Die
// Mails selbst liegen im React-Query-Cache (api/mail.ts).

export interface MailFilter {
  /** Konto-Adresse; "" = alle Postfächer. */
  acc: string
  /** Kategorie; "" = Posteingang (alles ohne Kategorie). */
  cat: string
  q: string
}

/** Vorbelegung für ✉ Schreiben (Antworten/Weiterleiten). */
export interface Draft {
  from?: string
  to?: string
  subject?: string
  body?: string
  /** Message-ID der beantworteten Mail. */
  reply?: string
}

interface MailStore {
  filter: MailFilter
  /** Auswahl für Sammel-Aktionen: "konto|uid". */
  sel: Set<string>
  draft: Draft
  setFilter: (f: Partial<MailFilter>) => void
  setSel: (sel: Set<string>) => void
  toggle: (key: string, on: boolean) => void
  setDraft: (d: Draft) => void
}

export const mailKey = (m: Pick<MailSummary, 'account' | 'uid'>) => `${m.account}|${m.uid}`

export const useMailStore = create<MailStore>((set) => ({
  filter: { acc: '', cat: '', q: '' },
  sel: new Set(),
  draft: {},
  setFilter: (f) => set((s) => ({ filter: { ...s.filter, ...f } })),
  setSel: (sel) => set({ sel }),
  toggle: (key, on) =>
    set((s) => {
      const sel = new Set(s.sel)
      if (on) sel.add(key)
      else sel.delete(key)
      return { sel }
    }),
  setDraft: (draft) => set({ draft }),
}))
