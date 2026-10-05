import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPost } from '@/lib/api'
import { useSettings } from '@/stores/settings'

// Team-Modus: die Firma aus KI-Mitarbeitern (server/team/, routes/team.py).
// Alles unter /api/team/ und nur, wenn ⚙ → Team an ist.

export type Modell = 'fable' | 'opus' | 'sonnet' | 'haiku'
export type Effort = 'low' | 'medium' | 'high' | 'xhigh' | 'max'
export type Berechtigung = 'acceptEdits' | 'auto' | 'bypassPermissions'

export interface Agent {
  slug: string
  name: string
  title: string
  reports_to: string
  model: Modell
  effort: Effort
  model_grund: string
  permission_mode: Berechtigung
  cwd: string
  allowed_tools: string[]
  can_delegate: boolean
  delegates_to: string[]
  /** r,g,b — fließt als --accent-rgb in alles, was der Person gehört. */
  color: string
  avatar: string
  status: 'active' | 'paused' | 'fired'
  hired: string
  max_stille_s: number
  /** Was an der Akte nicht stimmt (sie bleibt lesbar). */
  problems: string[]
  soul: string
  memory: string
}

export interface OrgNode {
  slug: string
  name: string
  title: string
  color: string
  model: string
  effort: string
  status: string
  problems: string[]
  reports: OrgNode[]
}

export interface Belegschaft {
  agents: Agent[]
  org: { roots: OrgNode[]; cycles: string[] }
}

export type AuftragStatus = 'neu' | 'laeuft' | 'wartet_auf_kevin' | 'fertig' | 'abgebrochen'

export interface Verbrauch {
  hops: number
  cost: number
  start: number
  je_agent?: Record<string, number>
}

export interface Eskalation {
  bremse: string
  grund: string
  frage: string
  seit: number
  /** Wer eskaliert hat — Antwort und „weitermachen“ gehen dorthin zurück. */
  an: string
}

export interface Auftrag {
  id: string
  titel: string
  brief: string
  status: AuftragStatus
  owner: string
  cwd: string
  erstellt: string
  in_arbeit: { msg_id: string; run_id: string; versuch: number } | null
  verbraucht: Verbrauch
  eskalation: Eskalation | null
  ergebnis?: string
}

/** Eine Zeile der Auftragsliste — mit Nachrichtenzahl, damit Ungelesenes auffällt. */
export interface AuftragKurz {
  id: string
  titel: string
  status: AuftragStatus
  owner: string
  erstellt: string
  verbraucht: Verbrauch
  eskalation: Eskalation | null
  msgs: number
  letzte_von: string
  letzte_art: string
  letzte_ts: number
}

export type NachrichtArt =
  | 'auftrag'
  | 'frage'
  | 'antwort'
  | 'ergebnis'
  | 'notiz'
  | 'einwurf'
  | 'gesagt'
  | 'system'
  | 'zugestellt'

export interface Nachricht {
  id: string
  ts: number
  von: string
  an: string
  art: NachrichtArt
  text: string
  dateien?: string[]
  groesse?: string
  bremse?: string
}

export interface Person {
  name: string
  title: string
  color: string
  avatar: string
}

export interface AuftragDetail {
  ticket: Auftrag
  verlauf: Nachricht[]
  agents: Record<string, Person>
}

export interface TeamStand {
  aktiv: {
    agent: string
    name: string
    color: string
    ticket: string
    titel: string
    seit: number
  }[]
  wartend: { id: string; titel: string; grund: string }[]
  pausiert: boolean
}

export interface AgentGespraech {
  session_id: string
  messages: { role: 'user' | 'assistant'; text: string; ts?: string; uuid?: string }[]
  umfang: { bytes: number; msgs: number; max_bytes: number; max_msgs: number }
  memory: string
  agent: Pick<
    Agent,
    'slug' | 'name' | 'title' | 'color' | 'model' | 'effort' | 'cwd' | 'permission_mode' | 'avatar'
  >
}

/** Läuft der Team-Modus? Ein Schalter für Ansichten, Leiste und Befehle. */
export const useTeamAn = () => useSettings((st) => st.settings.team?.aktiv === true)

const P = '/api/team'

export const useBelegschaft = () => {
  const an = useTeamAn()
  return useQuery({
    queryKey: ['team', 'agents'],
    queryFn: () => apiGet<Belegschaft>(`${P}/agents`),
    enabled: an,
    refetchOnMount: 'always',
  })
}

export const useAgent = (slug: string | null) =>
  useQuery({
    queryKey: ['team', 'agent', slug],
    queryFn: () => apiGet<Agent>(`${P}/agent/${encodeURIComponent(slug!)}`),
    enabled: !!slug,
    refetchOnMount: 'always',
  })

export const useAgentGespraech = (slug: string | null) =>
  useQuery({
    queryKey: ['team', 'agent', slug, 'chat'],
    queryFn: () => apiGet<AgentGespraech>(`${P}/agent/${encodeURIComponent(slug!)}/chat`),
    enabled: !!slug,
    refetchOnMount: 'always',
  })

export function useAgentActions() {
  const qc = useQueryClient()
  const neu = () => void qc.invalidateQueries({ queryKey: ['team'] })
  return {
    speichern: useMutation({
      mutationFn: (v: { slug: string } & Partial<Record<string, unknown>>) =>
        apiPost<{ agent: Agent; problems: string[] }>(
          `${P}/agent/${encodeURIComponent(v.slug)}`,
          v,
        ),
      onSuccess: neu,
    }),
    entlassen: useMutation({
      mutationFn: (slug: string) =>
        apiDelete<{ ok: boolean }>(`${P}/agent/${encodeURIComponent(slug)}`),
      onSuccess: neu,
    }),
    gespraechLeeren: useMutation({
      mutationFn: (slug: string) =>
        apiDelete<{ ok: boolean }>(`${P}/agent/${encodeURIComponent(slug)}/chat`),
      onSuccess: neu,
    }),
  }
}

export const useUserMd = () =>
  useQuery({
    queryKey: ['team', 'user-md'],
    queryFn: () => apiGet<{ text: string; ergaenzungen: string; protocol: string }>(`${P}/user-md`),
    refetchOnMount: 'always',
  })

export function useUserMdSpeichern() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { text?: string; ergaenzungen?: string }) =>
      apiPost<{ ok: boolean }>(`${P}/user-md`, v),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['team', 'user-md'] }),
  })
}

// ---------- Aufträge ----------
export const useAuftraege = () => {
  const an = useTeamAn()
  return useQuery({
    queryKey: ['team', 'auftraege'],
    queryFn: () => apiGet<{ tickets: AuftragKurz[] }>(`${P}/auftraege`).then((d) => d.tickets),
    enabled: an,
    refetchOnMount: 'always',
    // Der Server hat für die Liste keinen eigenen Strom: wo gearbeitet wird, alle
    // 4 s nachsehen, sonst alle 15 s. Bei unsichtbarem Fenster gar nicht (Vorgabe
    // von React Query) — vorher waren es auch nachts über 40 000 Anfragen, die
    // niemand las.
    refetchInterval: (q) => (q.state.data?.some((t) => t.status === 'laeuft') ? 4000 : 15000),
  })
}

export const useAuftrag = (id: string | null) =>
  useQuery({
    queryKey: ['team', 'auftrag', id],
    queryFn: () => apiGet<AuftragDetail>(`${P}/auftraege/${encodeURIComponent(id!)}`),
    enabled: !!id,
    refetchOnMount: 'always',
    refetchInterval: (q) => (q.state.data?.ticket.status === 'laeuft' ? 2500 : 10000),
  })

export const useTeamStand = () => {
  const an = useTeamAn()
  return useQuery({
    queryKey: ['team', 'state'],
    queryFn: () => apiGet<TeamStand>(`${P}/state`),
    enabled: an,
    refetchInterval: (q) => (q.state.data?.aktiv.length ? 4000 : 15000),
  })
}

export function useAuftragActions(id: string) {
  const qc = useQueryClient()
  const neu = () => void qc.invalidateQueries({ queryKey: ['team'] })
  const url = (rest = '') => `${P}/auftraege/${encodeURIComponent(id)}${rest}`
  return {
    antwort: useMutation({
      mutationFn: (v: { aktion: 'weiter' | 'abbrechen'; text?: string; an?: string }) =>
        apiPost<{ ticket: Auftrag }>(url('/antwort'), v),
      onSuccess: neu,
    }),
    say: useMutation({
      mutationFn: (v: { text: string; an?: string }) =>
        apiPost<{ ok: boolean; wohin: string }>(url('/say'), v),
      onSuccess: neu,
    }),
    loeschen: useMutation({
      mutationFn: () => apiDelete<{ ok: boolean }>(url()),
      onSuccess: neu,
    }),
  }
}

export function useAuftragNeu() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { brief: string; titel?: string; cwd?: string }) =>
      apiPost<{ ticket: Auftrag }>(`${P}/auftraege`, v),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['team'] }),
  })
}

export function useNotAus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (pause: boolean) => apiPost<{ pausiert: boolean }>(`${P}/pause`, { pause }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['team', 'state'] }),
  })
}

/** Ungelesenes: gemerkt wird, wie viele Nachrichten man in einem Auftrag zuletzt
 *  gesehen hat; alles darüber ist neu. Das steht im Browser und nicht auf dem
 *  Server — es ist eine Eigenschaft dieses Bildschirms, nicht der Firma. */
const GESEHEN = (id: string) => `construct:gesehen:${id}`
export const gesehen = (id: string) => Number(localStorage.getItem(GESEHEN(id)) ?? 0) || 0
export const merkeGesehen = (id: string, n: number) => {
  try {
    localStorage.setItem(GESEHEN(id), String(n))
  } catch {
    /* privater Modus o. Ä.: dann eben nicht */
  }
}
/** Was Kevin selbst zuletzt geschrieben hat, ist nie ungelesen. */
export const ungelesen = (t: AuftragKurz) =>
  Math.max(0, t.msgs - gesehen(t.id) - (t.letzte_von === 'kevin' ? 1 : 0))

/** Aus einem Ticket einen Auftrag machen: die Nachrichten des Tickets werden das Briefing. */
export function useFirmaGeben() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { session: string; nr: number }) =>
      apiPost<{ ticket: Auftrag }>(`${P}/auftraege/aus-ticket`, v),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['team'] })
      void qc.invalidateQueries({ queryKey: ['tickets'] })
    },
  })
}
