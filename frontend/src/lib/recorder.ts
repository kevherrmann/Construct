// Sprachaufnahme im Browser für die Spracheingabe (Composer → /api/stt).
// Chrome/Firefox nehmen WebM/Opus auf, Safari und das Mac-Fenster (WKWebView)
// MP4/AAC — Gemini versteht beides. Das Mikrofon wird nach jeder Aufnahme
// wieder freigegeben, sonst bliebe die Aufnahme-Anzeige des Systems an.

const TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

export const canRecord = () =>
  typeof window !== 'undefined' &&
  !!navigator.mediaDevices?.getUserMedia &&
  typeof window.MediaRecorder !== 'undefined'

export interface Recording {
  /** Beenden und die Aufnahme liefern. */
  stop: () => Promise<Blob>
  /** Verwerfen. */
  cancel: () => void
}

export async function startRecording(): Promise<Recording> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const mimeType = TYPES.find((t) => MediaRecorder.isTypeSupported(t))
  const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
  const chunks: Blob[] = []
  rec.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data)
  }
  const release = () => stream.getTracks().forEach((t) => t.stop())
  rec.start()
  return {
    stop: () =>
      new Promise((resolve) => {
        rec.onstop = () => {
          release()
          resolve(new Blob(chunks, { type: rec.mimeType || mimeType || 'audio/webm' }))
        }
        rec.stop()
      }),
    cancel: () => {
      rec.onstop = release
      if (rec.state !== 'inactive') rec.stop()
      else release()
    },
  }
}

/** Aufnahme → Text (Gemini 3.5 Transcribe über den Server). */
export async function transcribe(blob: Blob): Promise<string> {
  const ext = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm'
  const fd = new FormData()
  fd.append('file', blob, `aufnahme.${ext}`)
  const r = await fetch('/api/stt', { method: 'POST', body: fd })
  const j = (await r.json().catch(() => ({}))) as { text?: string; error?: string }
  if (!r.ok) throw new Error(j.error ?? `${r.status}`)
  return (j.text ?? '').trim()
}
