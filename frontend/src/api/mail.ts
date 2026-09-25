// E-Mail: Konten + IMAP/SMTP laufen im Backend (mail.py, Routen /api/mail/* in
// app.py). Kategorien sind rein lokal (nur hier in CONSTRUCT) — Löschen passiert
// dagegen ECHT auf dem Server (Papierkorb).
import { useQuery, type QueryClient } from '@tanstack/react-query'
import { ApiError, apiGet, apiPost } from '@/lib/api'

/** mail.public_accounts() — Zugangsdaten verlassen den Server nie. */
export interface MailAccount {
  email: string
  /** Anzeigename des Anbieters: "GMX", "Gmail", "Outlook/Hotmail" oder "?". */
  provider: string
  auth: 'password' | 'oauth'
  /** Deutscher Einrichtungshinweis des Anbieters (leer, wenn unbekannt). */
  hint: string
  configured: boolean
}

/** Ein Eintrag aus mail.list_messages() + Kategorie aus list_all(). */
export interface MailSummary {
  account: string
  folder: string
  /** IMAP-UID als Text. */
  uid: string
  /** Stabiler Schlüssel für die lokale Kategorie-Zuordnung (Message-ID o. Ä.). */
  key: string
  from_name: string
  from_addr: string
  to: string
  subject: string
  /** Unix-Zeit in Sekunden (0 = unbekannt). */
  ts: number
  seen: boolean
  /** "" = keine Kategorie (Posteingang). */
  category: string
}

export interface MailList {
  messages: MailSummary[]
  /** Konto → Fehlermeldung; Konten mit Fehler fehlen in messages. */
  errors: Record<string, string>
}

export interface MailAttachment {
  /** Index im MIME-Baum — Parameter idx für /api/mail/att. */
  idx: number
  name: string
  size: number
  mime: string
}

/** mail.get_message() */
export interface MailMessage {
  account: string
  folder: string
  uid: string
  key: string
  message_id: string
  from_name: string
  from_addr: string
  to: string
  cc: string
  subject: string
  ts: number
  text: string
  /** Mit eingebetteten cid:-Bildern als data:-URIs; "" = reine Textmail. */
  html: string
  attachments: MailAttachment[]
}

/** Antwort von /api/mail/attach — path geht beim Senden unverändert zurück. */
export interface UploadedAttachment {
  path: string
  name: string
  size: number
}

export interface DeleteManyResult {
  ok: boolean
  deleted: number
  errors: Record<string, string>
}

export interface MailRef {
  account: string
  uid: string
  folder: string
}

export interface SendMail {
  account: string
  to: string
  cc: string
  subject: string
  body: string
  attachments: { path: string; name: string }[]
  /** Message-ID der beantworteten Mail ("" = neue Mail). */
  reply: string
}

export type MsPoll = { ok: true } | { pending: true } | { error: string }

export const MAIL_KEYS = {
  accounts: ['mail', 'accounts'] as const,
  categories: ['mail', 'categories'] as const,
  list: ['mail', 'list'] as const,
  msg: (r: MailRef) => ['mail', 'msg', r.account, r.folder, r.uid] as const,
}

/** Schlüssel der Sammelfehlermeldung, wenn der ganze Abruf scheitert. */
export const FETCH_ERROR = '__abruf__'

export async function fetchMailList(force: boolean): Promise<MailList> {
  // limit=9999 = praktisch alle. (Bewusst nicht 0: der alte Server-Code würde
  // 0 auf 1 Mail kappen — 9999 heißt dort einfach 200, also kein Schaden.)
  try {
    const j = await apiGet<MailList>(`/api/mail/list?limit=9999${force ? '&force=1' : ''}`)
    return { messages: j.messages ?? [], errors: j.errors ?? {} }
  } catch (e) {
    // Wie die alte Oberfläche: Liste leer, Fehler oben als Hinweis — kein
    // Fehlerzustand, der die Seite blockiert.
    return { messages: [], errors: { [FETCH_ERROR]: errText(e) } }
  }
}

export const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))

const q = (r: MailRef) =>
  `account=${encodeURIComponent(r.account)}&uid=${encodeURIComponent(r.uid)}&folder=${encodeURIComponent(r.folder || 'INBOX')}`

export const attachmentUrl = (r: MailRef, idx: number) => `/api/mail/att?${q(r)}&idx=${idx}`

export const useMailAccounts = () =>
  useQuery({
    queryKey: MAIL_KEYS.accounts,
    queryFn: async () => (await apiGet<{ accounts: MailAccount[] }>('/api/mail/accounts')).accounts,
  })

export const useMailCategories = () =>
  useQuery({
    queryKey: MAIL_KEYS.categories,
    queryFn: async () =>
      (await apiGet<{ categories: string[] }>('/api/mail/categories')).categories,
  })

/**
 * Alle Mails aller eingerichteten Konten. Kein automatisches Nachladen: der
 * Abruf kann bei großen Postfächern eine Minute dauern und würde lokale
 * Änderungen (gelesen, Kategorie, gelöscht) überschreiben. Geladen wird beim
 * Öffnen der Ansicht und über ⟲ AKTUALISIEREN (siehe refreshMailList).
 */
export const useMailList = (enabled: boolean) =>
  useQuery({
    queryKey: MAIL_KEYS.list,
    queryFn: () => fetchMailList(false),
    enabled,
    staleTime: Infinity,
    retry: false,
  })

/** force=1 umgeht den Listen-Cache des Servers (sonst gilt dort LIST_TTL). */
export const refreshMailList = (qc: QueryClient, force: boolean) =>
  qc.fetchQuery({ queryKey: MAIL_KEYS.list, queryFn: () => fetchMailList(force), staleTime: 0 })

export const useMailMessage = (r: MailRef | null) =>
  useQuery({
    queryKey: r ? MAIL_KEYS.msg(r) : ['mail', 'msg', 'none'],
    queryFn: () => apiGet<MailMessage>(`/api/mail/msg?${q(r!)}`),
    enabled: !!r,
    // Jedes Öffnen fragt neu — der Server markiert dabei als gelesen.
    gcTime: 0,
    retry: false,
  })

/** Liste im Cache anpassen, ohne neu abzurufen (Abruf ist teuer, s. o.). */
export function patchMailList(qc: QueryClient, fn: (msgs: MailSummary[]) => MailSummary[]) {
  qc.setQueryData<MailList>(MAIL_KEYS.list, (cur) =>
    cur ? { ...cur, messages: fn(cur.messages) } : cur,
  )
}

export const mailApi = {
  saveAccount: (email: string, password: string) =>
    apiPost<{ ok: true }>('/api/mail/accounts', { email, password }),
  deleteAccount: (email: string) =>
    apiGet<{ ok: true }>(`/api/mail/accounts/${encodeURIComponent(email)}`, { method: 'DELETE' }),
  test: (email: string) => apiPost<{ ok: true; inbox: number }>('/api/mail/test', { email }),
  msLogin: (email: string) =>
    apiPost<{ url: string; code: string }>('/api/mail/ms_login', { email }),
  msPoll: (email: string) => apiGet<MsPoll>(`/api/mail/ms_poll?email=${encodeURIComponent(email)}`),
  delete: (r: MailRef) =>
    apiPost<{ ok: true }>('/api/mail/delete', { ...r, folder: r.folder || 'INBOX' }),
  // Die Rückfallebene der alten Oberfläche (einzeln löschen, wenn der Server
  // delete_many noch nicht kennt) entfällt: /next wird immer mit dem passenden
  // Backend ausgeliefert.
  deleteMany: (items: MailRef[]) => apiPost<DeleteManyResult>('/api/mail/delete_many', { items }),
  flag: (r: MailRef, seen: boolean) =>
    apiPost<{ ok: true }>('/api/mail/flag', { ...r, folder: r.folder || 'INBOX', seen }),
  send: (b: SendMail) => apiPost<{ ok: true }>('/api/mail/send', b),
  editCategories: (p: { add?: string; remove?: string }) =>
    apiPost<{ categories: string[] }>('/api/mail/categories', p),
  categorize: (key: string, category: string) =>
    apiPost<{ ok: true }>('/api/mail/categorize', { key, category }),
  categorizeMany: (keys: string[], category: string) =>
    apiPost<{ ok: true; count: number }>('/api/mail/categorize_many', { keys, category }),
  /** Multipart geht nicht über apiPost (JSON) — Fehler trotzdem als ApiError. */
  async attach(file: File): Promise<UploadedAttachment> {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch('/api/mail/attach', { method: 'POST', body: fd })
    let body: unknown = null
    try {
      body = await res.json()
    } catch {
      /* kein JSON — unten generische Meldung */
    }
    const j = (body ?? {}) as Partial<UploadedAttachment> & { error?: string }
    if (!res.ok || !j.path) throw new ApiError(j.error || `HTTP ${res.status}`, res.status)
    return j as UploadedAttachment
  },
}
