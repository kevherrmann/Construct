import { trServer } from '@/lib/serverText'
import i18n from 'i18next'
import { tk } from '@/lib/i18n'
import { create } from 'zustand'
import type { SessionDetail, SessionInfo } from '@/api/chat'
import { apiGet, apiPost } from '@/lib/api'
import { addRunNote, applyEvent, initialRun, newId, type RunState } from '@/lib/chat/reducer'
import { SseParser } from '@/lib/chat/sse'
import { DEFAULT_MODEL, MODES, type Mode } from '@/lib/chat/models'
import type { BotItem, ChatItem, NoteText, SysBody, TranscriptMessage } from '@/lib/chat/types'
import { queryClient } from '@/lib/queryClient'
import { getItem, setItem } from '@/lib/storage'
import { useSettings } from './settings'
import { say } from '@/lib/audio'
import { speakableText } from '@/lib/chat/speak'

// Mehrere parallele Unterhaltungen (wie mehrere Terminals): jede hat EIGENEN
// Zustand — Session, laufender Stream, Warteschlange, Verlauf. Wechseln blendet
// nur um; die laufende Antwort einer anderen Session läuft im Hintergrund weiter.

export interface Attachment {
  path: string
  url: string
  name: string
}

interface Queued {
  text: string
  images: string[]
  urls: string[]
}

export interface Conv {
  key: string
  sessionId: string | null
  cwd: string | null
  /** An DIESE Session gebunden; neue erben die zuletzt gewählte Vorgabe. */
  model: string
  /** Womit zuletzt WIRKLICH geantwortet wurde (Statuszeile). */
  lastModel: string
  busy: boolean
  /** Zug fertig, aber claude wartet noch auf eigene Hintergrundaufgaben. */
  nachlauf: boolean
  runId: string | null
  stopReq: boolean
  queue: Queued[]
  /** Byte-Position für den Live-Tail; null = beim nächsten Mal neu synchronisieren. */
  fileOffset: number | null
  history: ChatItem[]
  /** Anzeige des laufenden Laufs — wird bei jedem Reconnect aus dem Replay neu gebaut. */
  run: RunState | null
}

interface ChatStore {
  convs: Record<string, Conv>
  activeKey: string | null
  /** Anhänge für die nächste Nachricht (gelten für die aktive Unterhaltung). */
  pending: Attachment[]
  mode: Mode
  /** Ordner-Auswahl unten; gilt ab dem ersten Senden fest für die Session. */
  folder: string | null
  /** Zähler: steigt, wenn das Eingabefeld den Fokus zurückbekommen soll. */
  focusTick: number

  active: () => Conv | undefined
  newSession: () => void
  activate: (key: string) => void
  openSession: (s: SessionInfo, runningRunId?: string) => Promise<void>
  send: (text: string) => Promise<void>
  resend: (itemId: string, text: string) => void
  stop: () => void
  removeQueued: (i: number) => void
  clear: () => void
  addSys: (sys: SysBody) => void
  addNote: (note: NoteText) => void
  setModel: (v: string) => void
  setMode: (v: string) => void
  setFolder: (path: string) => void
  addPending: (a: Attachment) => void
  removePending: (i: number) => void
  pollTail: () => Promise<void>
  forgetSession: (sessionId: string) => void
}

const workspace = () => useSettings.getState().boot.workspace

/** Noch nie etwas gewählt → Opus 5.5. Ein bewusst gewähltes "Standard" ist '' und bleibt es. */
export const storedModel = () => getItem('mxmodel') ?? DEFAULT_MODEL
const storedMode = (): Mode => {
  const v = getItem('mxmode')
  return MODES.some((m) => m.v === v) ? (v as Mode) : 'bypassPermissions'
}

function makeConv(opts: Partial<Conv> = {}): Conv {
  return {
    key: newId('conv'),
    sessionId: null,
    cwd: null,
    model: storedModel(),
    lastModel: '',
    busy: false,
    nachlauf: false,
    runId: null,
    stopReq: false,
    queue: [],
    fileOffset: null,
    history: [],
    run: null,
    ...opts,
  }
}

export const transcriptItems = (msgs: TranscriptMessage[]): ChatItem[] =>
  msgs.map((m) =>
    m.role === 'user'
      ? { kind: 'user', id: newId('u'), text: m.text, urls: [], editable: true }
      : { kind: 'bot', id: newId('b'), blocks: [], thinking: false, markdown: m.text },
  )

const note = (key: string, center = false): ChatItem => ({
  kind: 'note',
  id: newId('n'),
  note: { key },
  center,
})

const refreshLists = () => {
  void queryClient.invalidateQueries({ queryKey: ['sessions'] })
}

// Streams laufen außerhalb von React; AbortController je Unterhaltung.
const streamCtrl = new Map<string, AbortController>()

export const useChat = create<ChatStore>((set, get) => {
  const patch = (key: string, p: Partial<Conv> | ((c: Conv) => Partial<Conv>)) =>
    set((s) => {
      const c = s.convs[key]
      if (!c) return s
      return { convs: { ...s.convs, [key]: { ...c, ...(typeof p === 'function' ? p(c) : p) } } }
    })
  const conv = (key: string) => get().convs[key]

  function finishRun(key: string) {
    const c = conv(key)
    if (!c) return
    streamCtrl.delete(key)
    patch(key, {
      history: [...c.history, ...(c.run?.items ?? [])],
      run: null,
      runId: null,
      busy: false,
      nachlauf: false,
      stopReq: false,
      // Tail-Position neu synchronisieren — der Lauf wurde ja live gezeigt.
      fileOffset: null,
    })
    if (get().activeKey === key) set((s) => ({ focusTick: s.focusTick + 1 }))
    refreshLists()
    void queryClient.invalidateQueries({ queryKey: ['usage'] })
    void queryClient.invalidateQueries({ queryKey: ['auth-status'] })
    const next = conv(key)?.queue[0]
    if (next) {
      patch(key, (cc) => ({ queue: cc.queue.slice(1) }))
      void runSend(key, next.text, next.images, next.urls)
    }
  }

  // Dockt an conv.runId an: spielt erst den Backlog nach, dann live — und
  // verbindet sich bei Aussetzern (Reload, Schlaf, Netz) neu. Der Lauf selbst
  // läuft serverseitig weiter.
  async function consumeRun(key: string) {
    let finished = false
    while (!finished) {
      const c = conv(key)
      if (!c?.runId || c.stopReq) break
      // Bei jedem (Re)Connect frisch aus dem Replay aufbauen.
      let rs = initialRun()
      let frame = 0
      const flush = () => {
        frame = 0
        patch(key, { run: rs })
      }
      // Viele kleine Text-Deltas: höchstens einmal pro Bild zeichnen.
      const schedule = () => {
        if (!frame) frame = requestAnimationFrame(flush)
      }
      patch(key, { run: rs })
      const ctrl = new AbortController()
      streamCtrl.set(key, ctrl)
      let watchdog: ReturnType<typeof setTimeout> | undefined
      const bump = () => {
        clearTimeout(watchdog)
        watchdog = setTimeout(() => ctrl.abort('idle'), 40000)
      }
      let dropped = false
      try {
        bump()
        const res = await fetch(`/api/stream/${encodeURIComponent(c.runId)}`, {
          signal: ctrl.signal,
        })
        if (res.status === 404) {
          rs = addRunNote(rs, {
            t: 'note',
            note: {
              key: tk('⚠ Lauf nicht mehr verfügbar (zu alt/aufgeräumt). Schick einfach nochmal.'),
            },
          })
          flush()
          finished = true
          break
        }
        const reader = res.body!.getReader()
        const dec = new TextDecoder()
        const parser = new SseParser()
        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          bump()
          for (const ev of parser.push(dec.decode(value, { stream: true }))) {
            rs = applyEvent(rs, ev)
            switch (ev.type) {
              case 'session':
                patch(key, { sessionId: ev.session_id })
                refreshLists()
                break
              case 'stats':
                if (ev.model) patch(key, { lastModel: ev.model })
                break
              case 'nachlauf':
                // Prozess bleibt offen, der Nutzer darf tippen (geht per inject
                // in denselben Prozess).
                patch(key, { nachlauf: true, busy: false })
                break
              case 'neuer_zug':
                patch(key, { nachlauf: false, busy: true })
                break
              case 'nachlauf_ende':
                patch(key, { nachlauf: false })
                break
              case 'done': {
                if (ev.session_id) patch(key, { sessionId: ev.session_id })
                if (!conv(key)?.nachlauf) finished = true
                const st = useSettings.getState()
                const turn = [...rs.items].reverse().find((i): i is BotItem => i.kind === 'bot')
                if (st.settings.tts.auto && get().activeKey === key && turn)
                  void say(speakableText(turn.blocks), { owner: turn.id }).catch(() => {})
                break
              }
              case 'error':
                finished = true
                break
            }
            if (ev.type === 'text') schedule()
            else flush()
          }
        }
        if (frame) cancelAnimationFrame(frame)
        flush()
        clearTimeout(watchdog)
        if (!finished && !conv(key)?.stopReq) dropped = true // Stream zu, Lauf nicht fertig
      } catch {
        clearTimeout(watchdog)
        if (conv(key)?.stopReq) finished = true
        else dropped = true
      }
      if (dropped && !conv(key)?.stopReq) {
        if (get().activeKey === key) {
          rs = addRunNote(rs, {
            t: 'note',
            note: { key: tk('… Verbindung verloren – dock wieder an …') },
          })
          flush()
        }
        await new Promise((r) => setTimeout(r, 1000))
      }
    }
    const c = conv(key)
    if (c?.stopReq && c.run)
      patch(key, { run: addRunNote(c.run, { t: 'note', note: { key: tk('⏹ Gestoppt.') } }) })
    finishRun(key)
  }

  // Startet einen entkoppelten Lauf: POST holt die run_id, dann dockt consumeRun an.
  async function runSend(key: string, text: string, images: string[], urls: string[]) {
    const c0 = conv(key)
    if (!c0) return
    // cwd beim ersten Senden festschreiben, damit parallele Sessions stabil bleiben.
    const cwd = c0.cwd ?? get().folder ?? workspace()
    const user: ChatItem = { kind: 'user', id: newId('u'), text, urls, editable: true }
    patch(key, { busy: true, stopReq: false, cwd, history: [...c0.history, user] })
    try {
      const j = await apiPost<{ run_id?: string; session_id?: string; error?: string }>(
        '/api/chat',
        {
          message: text,
          session_id: c0.sessionId,
          images,
          cwd,
          mode: get().mode,
          model: c0.model || '',
        },
      )
      if (!j.run_id) throw new Error(j.error ?? 'keine run_id')
      patch(key, (c) => ({ runId: j.run_id!, sessionId: j.session_id ?? c.sessionId }))
    } catch (e) {
      const err = e as Error & { status?: number }
      const failed: BotItem = {
        kind: 'bot',
        id: newId('b'),
        thinking: false,
        blocks: [
          {
            t: 'error',
            message: i18n.t(tk('⚠ Konnte Anfrage nicht starten: {e}'), {
              // Die Meldung des Servers hat Vorrang; nur ein nacktes 401 wird erklärt.
              e:
                err.status === 401 && /^401\b/.test(err.message)
                  ? i18n.t(tk('Nicht angemeldet (Passwort?)'))
                  : trServer(err.message),
            }),
          },
        ],
      }
      patch(key, (c) => ({ history: [...c.history, failed] }))
      finishRun(key)
      return
    }
    await consumeRun(key)
  }

  const first = makeConv({
    history: [note(tk('⌁ Neue Session — Ordner unten wählbar, dann schreib los ⌁'), true)],
  })

  return {
    convs: { [first.key]: first },
    activeKey: first.key,
    pending: [],
    mode: storedMode(),
    folder: null,
    focusTick: 0,

    active: () => {
      const k = get().activeKey
      return k ? get().convs[k] : undefined
    },

    newSession() {
      const c = makeConv({
        history: [note(tk('⌁ Neue Session — Ordner unten wählbar, dann schreib los ⌁'), true)],
      })
      set((s) => ({
        convs: { ...s.convs, [c.key]: c },
        activeKey: c.key,
        // Neue Session beginnt im Arbeitsordner, nicht im Ordner der zuletzt
        // angesehenen — sonst landete die nächste Nachricht unbemerkt dort.
        folder: workspace() || s.folder,
        focusTick: s.focusTick + 1,
      }))
      refreshLists()
    },

    activate(key) {
      const c = conv(key)
      if (!c) return
      set({ activeKey: key, folder: c.cwd ?? (workspace() || get().folder) })
    },

    async openSession(s, runningRunId) {
      // Läuft diese Session schon hier (offen / gerade am Antworten)? Dann nur
      // wieder einblenden — Stream und Verlauf bleiben unangetastet.
      const existing = Object.values(get().convs).find((c) => c.sessionId === s.id)
      if (existing) {
        get().activate(existing.key)
        refreshLists()
        return
      }
      const cwd = s.cwd || workspace()
      const c = makeConv({
        sessionId: s.id,
        cwd,
        history: [note(tk('⟲ Lade Verlauf …'))],
        // Läuft serverseitig noch ein Lauf (z. B. nach Reload)? Dann nach dem
        // Verlauf live wieder andocken (Backlog-Replay + weiter live).
        runId: runningRunId ?? null,
        busy: !!runningRunId,
      })
      set((st) => ({ convs: { ...st.convs, [c.key]: c }, activeKey: c.key, folder: cwd }))
      let j: Partial<SessionDetail> = {}
      try {
        j = await apiGet<SessionDetail>(
          `/api/sessions/${encodeURIComponent(s.project)}/${encodeURIComponent(s.id)}`,
        )
      } catch {
        /* leer anzeigen */
      }
      const items = transcriptItems(j.messages ?? [])
      patch(c.key, {
        ...(j.model ? { model: j.model, lastModel: j.model } : {}),
        // ab hier übernimmt der Live-Tail — außer ein Lauf dockt gleich an
        fileOffset: runningRunId ? null : (j.offset ?? null),
        history: items.length || runningRunId ? items : [note(tk('(leere Session)'))],
      })
      refreshLists()
      if (runningRunId) await consumeRun(c.key)
    },

    async send(text) {
      const c = get().active()
      if (!c) return
      const { pending } = get()
      const images = pending.map((p) => p.path)
      const urls = pending.map((p) => p.url)
      if (!text && !images.length) return
      set({ pending: [] })
      if (c.busy || c.nachlauf) {
        // Cody arbeitet gerade (oder wartet im Nachlauf auf eine Hintergrund-
        // aufgabe): Nachricht DIREKT in den laufenden Prozess einwerfen
        // (Steering). Klappt das nicht (Zug gerade fertig), normale
        // Warteschlange — im Nachlauf stattdessen ein frischer Lauf per --resume.
        if (c.runId) {
          try {
            await apiPost(`/api/inject/${encodeURIComponent(c.runId)}`, {
              message: text,
              images,
              urls,
            })
            if (conv(c.key)?.nachlauf) patch(c.key, { nachlauf: false, busy: true })
            return
          } catch {
            /* weiter unten */
          }
        }
        if (conv(c.key)?.nachlauf) patch(c.key, { nachlauf: false })
        else {
          patch(c.key, (cc) => ({ queue: [...cc.queue, { text, images, urls }] }))
          return
        }
      }
      await runSend(c.key, text, images, urls)
    },

    resend(itemId, text) {
      const c = get().active()
      if (!c || c.busy || !text.trim()) return
      const idx = c.history.findIndex((i) => i.id === itemId)
      // Nur wenn dies die LETZTE eigene Nachricht ist, räumen wir die
      // (gestoppte) Antwort darunter weg — bei älteren bleibt alles stehen.
      const laterUser = c.history.slice(idx + 1).some((i) => i.kind === 'user')
      if (idx >= 0 && !laterUser) patch(c.key, { history: c.history.slice(0, idx) })
      void runSend(c.key, text.trim(), [], [])
    },

    stop() {
      const c = get().active()
      if (!c?.runId) return
      patch(c.key, { stopReq: true, queue: [] })
      void fetch(`/api/stop/${encodeURIComponent(c.runId)}`, { method: 'POST' }).catch(() => {})
      streamCtrl.get(c.key)?.abort('user')
    },

    removeQueued(i) {
      const c = get().active()
      if (c) patch(c.key, { queue: c.queue.filter((_, j) => j !== i) })
    },

    clear() {
      const c = get().active()
      if (c) patch(c.key, { history: [] })
    },

    addSys(sys) {
      const c = get().active()
      if (c) patch(c.key, { history: [...c.history, { kind: 'sys', id: newId('s'), sys }] })
    },

    addNote(n) {
      const c = get().active()
      if (c) patch(c.key, { history: [...c.history, { kind: 'note', id: newId('n'), note: n }] })
    },

    // Gilt für die AKTIVE Session und wird Vorgabe für neue.
    setModel(v) {
      const c = get().active()
      if (c) patch(c.key, { model: v })
      setItem('mxmodel', v)
    },

    setMode(v) {
      const m = MODES.find((x) => x.v === v)?.v ?? 'bypassPermissions'
      setItem('mxmode', m)
      set({ mode: m })
    },

    setFolder(path) {
      set({ folder: path })
    },

    addPending(a) {
      set((s) => ({ pending: [...s.pending, a] }))
    },

    removePending(i) {
      set((s) => ({ pending: s.pending.filter((_, j) => j !== i) }))
    },

    // Live-Tail: läuft die geöffnete Session woanders (Terminal, Telegram,
    // anderer Browser), wächst ihre .jsonl-Datei — alle 3 s das Neue abholen.
    // Eigene Läufe streamen live über SSE (dann pausiert der Tail).
    async pollTail() {
      const c = get().active()
      if (!c || c.busy || c.nachlauf || !c.sessionId || document.hidden) return
      const sid = c.sessionId
      try {
        const j = await apiGet<{ offset: number | null; messages: TranscriptMessage[] }>(
          `/api/session_tail/${encodeURIComponent(sid)}?offset=${c.fileOffset ?? -1}`,
        )
        if (j.offset == null) return
        // Lage kann sich während des fetch geändert haben → nichts anfassen.
        const now = get().active()
        if (!now || now.key !== c.key || now.busy || now.sessionId !== sid) return
        const firstSync = now.fileOffset == null
        // Nichts Neues? Dann nichts anfassen — jede Änderung zeichnet neu, und
        // wer gerade nach oben scrollt, soll nicht alle 3 s zurückgerissen werden.
        if (!firstSync && j.offset === now.fileOffset && !j.messages?.length) return
        patch(c.key, (cc) => ({
          fileOffset: j.offset,
          // Beim ersten Mal nur Position merken — der Verlauf steht ja schon da.
          history: firstSync ? cc.history : [...cc.history, ...transcriptItems(j.messages ?? [])],
        }))
      } catch {
        /* nächster Versuch in 3 s */
      }
    },

    // Gelöschte Session: war sie offen, eine frische zeigen.
    forgetSession(sessionId) {
      const c = get().active()
      if (c?.sessionId === sessionId) get().newSession()
    },
  }
})
