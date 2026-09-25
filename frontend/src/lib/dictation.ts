// Spracheingabe live: Mikrofon → 16-kHz-PCM → WebSocket /api/stt/live →
// Gemini 3.5 Transcribe Live (server/stt.py). Der Text kommt zurück, während
// man noch spricht — je Äußerung erst vorläufig, nach der Sprechpause
// bereinigt ("final"). Das Mikrofon wird am Ende wieder freigegeben, sonst
// bliebe die Aufnahme-Anzeige des Systems an.

import { tk } from '@/lib/i18n'

export const RATE = 16000
/** 100 ms je Stück — so empfiehlt es die Live-API. */
const CHUNK = RATE / 10

// Läuft im Audio-Thread: mittelt die Abtastwerte auf 16 kHz herunter (die
// Hardware liefert meist 44,1 oder 48 kHz) und schickt 16-bit-Stücke hoch.
// Inline als Blob, damit der Build keine zusätzliche Datei ausliefern muss.
const WORKLET = `
class Pcm16 extends AudioWorkletProcessor {
  constructor(opts) {
    super()
    this.step = sampleRate / ${RATE}
    this.pos = 0; this.sum = 0; this.n = 0
    this.buf = new Int16Array(${CHUNK}); this.len = 0
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (!ch) return true
    for (let i = 0; i < ch.length; i++) {
      this.sum += ch[i]; this.n++; this.pos++
      if (this.pos >= this.step) {
        this.pos -= this.step
        const v = Math.max(-1, Math.min(1, this.sum / this.n))
        this.buf[this.len++] = v < 0 ? v * 0x8000 : v * 0x7fff
        this.sum = 0; this.n = 0
        if (this.len === this.buf.length) {
          this.port.postMessage(this.buf.buffer, [this.buf.buffer])
          this.buf = new Int16Array(${CHUNK}); this.len = 0
        }
      }
    }
    return true
  }
}
registerProcessor('pcm16', Pcm16)
`

export const canDictate = () =>
  typeof window !== 'undefined' &&
  !!navigator.mediaDevices?.getUserMedia &&
  typeof window.AudioWorkletNode !== 'undefined' &&
  typeof window.WebSocket !== 'undefined'

/** Setzt das Diktat zusammen: bereinigte Äußerungen + die laufende. */
export function joinSpoken(finals: string[], interim: string): string {
  return [...finals, interim]
    .map((t) => t.trim())
    .filter(Boolean)
    .join(' ')
}

export interface DictationEvents {
  /** Gesamter bisher erkannter Text (bereinigt + vorläufig). */
  onText: (text: string) => void
  /** Abbruch durch Server oder Netz (nicht durch cancel()). */
  onError: (message: string) => void
}

export interface Dictation {
  /** Aufnahme beenden, auf den letzten bereinigten Text warten, ihn liefern. */
  stop: () => Promise<string>
  /** Verwerfen. */
  cancel: () => void
}

export async function startDictation(ev: DictationEvents): Promise<Dictation> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  })
  const ctx = new AudioContext()
  let node: AudioWorkletNode
  try {
    const url = URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }))
    await ctx.audioWorklet.addModule(url)
    URL.revokeObjectURL(url)
    node = new AudioWorkletNode(ctx, 'pcm16')
  } catch (e) {
    stream.getTracks().forEach((t) => t.stop())
    void ctx.close()
    throw e
  }
  const source = ctx.createMediaStreamSource(stream)
  source.connect(node)

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/api/stt/live`)
  ws.binaryType = 'arraybuffer'
  // Bis die Verbindung steht, sammeln — die ersten Worte sollen nicht fehlen.
  const early: ArrayBuffer[] = []
  node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(e.data)
    else if (ws.readyState === WebSocket.CONNECTING) early.push(e.data)
  }
  ws.onopen = () => early.splice(0).forEach((b) => ws.send(b))

  const finals: string[] = []
  let interim = ''
  let over = false
  let settle: ((text: string) => void) | null = null

  let released = false
  const release = () => {
    if (released) return
    released = true
    node.port.onmessage = null
    source.disconnect()
    node.disconnect()
    stream.getTracks().forEach((t) => t.stop())
    void ctx.close()
  }
  const finish = () => {
    if (over) return
    over = true
    release()
    if (ws.readyState <= WebSocket.OPEN) ws.close()
    const text = joinSpoken(finals, interim)
    settle?.(text)
  }

  ws.onmessage = (e: MessageEvent<string>) => {
    let m: { interim?: string; final?: string; error?: string; done?: boolean }
    try {
      m = JSON.parse(e.data)
    } catch {
      return
    }
    if (m.interim !== undefined) interim = m.interim
    if (m.final !== undefined) {
      finals.push(m.final)
      interim = ''
    }
    if (m.interim !== undefined || m.final !== undefined) ev.onText(joinSpoken(finals, interim))
    if (m.error) {
      if (!over && !settle) ev.onError(m.error)
      finish()
    }
    if (m.done) finish()
  }
  ws.onclose = (e) => {
    if (!over && !settle && e.code !== 1000)
      ev.onError(`${tk('Verbindung zur Spracheingabe abgebrochen')} (${e.code})`)
    finish()
  }

  return {
    stop: () =>
      new Promise<string>((resolve) => {
        if (over) return resolve(joinSpoken(finals, interim))
        settle = resolve
        // Mikrofon sofort frei, der Server liefert nur noch den Rest nach.
        release()
        const end = () => ws.send('end')
        if (ws.readyState === WebSocket.OPEN) end()
        else ws.addEventListener('open', end)
        // Sicherheitsnetz, falls der Server nicht mehr antwortet.
        setTimeout(finish, 8000)
      }),
    cancel: () => {
      over = true
      release()
      ws.close()
    },
  }
}
