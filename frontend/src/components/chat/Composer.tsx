import { canRecord, startRecording, transcribe, type Recording } from '@/lib/recorder'
import { trServer } from '@/lib/serverText'
import { Surface } from '@/components/layout/Surface'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'
import { useFolders } from '@/api/chat'
import { useProviders } from '@/api/providers'
import { runCommand } from '@/lib/chat/commands'
import { isPdf } from '@/lib/format'
import { useChat, type Attachment } from '@/stores/chat'
import { Pickers, type PickerName } from './Pickers'
import s from './Composer.module.css'

const ATT_EXT = /\.(png|jpe?g|gif|webp|bmp|svg|heic|pdf)$/i

declare global {
  interface Window {
    /** desktop.py meldet unter WebKitGTK hereingezogene Dateien hierüber. */
    __nativeDrop?: (items: Attachment[]) => void
  }
}

async function upload(f: File): Promise<Attachment> {
  const fd = new FormData()
  fd.append('file', f)
  let j: { path?: string; url?: string; name?: string; error?: string }
  try {
    j = await (await fetch('/api/upload', { method: 'POST', body: fd })).json()
  } catch {
    j = {}
  }
  if (!j.path || !j.url) throw new Error(j.error ?? 'Upload fehlgeschlagen')
  return { path: j.path, url: j.url, name: j.name ?? f.name }
}

export function Composer() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const [text, setText] = useState('')
  const [picker, setPicker] = useState<PickerName | null>(null)
  const [dragging, setDragging] = useState(false)
  // Spracheingabe: Aufnahme läuft (Sekunden) bzw. wird gerade umgewandelt.
  const [rec, setRec] = useState<{ state: 'idle' | 'recording' | 'working'; secs: number }>({
    state: 'idle',
    secs: 0,
  })
  const [micError, setMicError] = useState('')
  const recording = useRef<Recording | null>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const file = useRef<HTMLInputElement>(null)
  const providers = useProviders()
  const folders = useFolders()
  const { pending, addPending, removePending, send, stop, removeQueued, focusTick } = useChat()
  const conv = useChat((st) => st.active())
  const busy = !!conv?.busy

  // Höhe mitwachsen lassen — höchstens einmal pro Bild. Die Folge "height=auto
  // schreiben → scrollHeight lesen" erzwingt ein Neu-Layout der ganzen Seite;
  // bei jedem Tastendruck war das spürbarer Tipp-Lag.
  const frame = useRef(0)
  const autosize = useCallback(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }, [])
  useEffect(() => {
    if (frame.current) return
    frame.current = requestAnimationFrame(() => {
      frame.current = 0
      autosize()
    })
  }, [text, autosize])

  useEffect(() => {
    if (focusTick) input.current?.focus()
  }, [focusTick])

  const addFiles = useCallback(
    (files: File[]) => {
      for (const f of files) upload(f).then(addPending, (e: Error) => alert(t(e.message)))
    },
    [addPending, t],
  )

  // Ziehen & Ablegen überall im Fenster. Im Desktop-Fenster unter WebKitGTK
  // kommen Dateien hier nur als Name an, nicht lesbar — dort übernimmt
  // desktop.py den Drop und meldet die Anhänge über __nativeDrop.
  useEffect(() => {
    const native = () => window.pywebview?.platform === 'gtkwebkit2'
    const over = (e: DragEvent) => {
      e.preventDefault()
      setDragging(true)
    }
    const leave = (e: DragEvent) => {
      if (e.relatedTarget === null) setDragging(false)
    }
    const drop = (e: DragEvent) => {
      e.preventDefault()
      setDragging(false)
      if (native()) return
      addFiles(
        [...(e.dataTransfer?.files ?? [])].filter(
          (f) => f.type.startsWith('image/') || ATT_EXT.test(f.name),
        ),
      )
    }
    window.__nativeDrop = (items) => items.forEach(addPending)
    addEventListener('dragover', over)
    addEventListener('dragleave', leave)
    addEventListener('drop', drop)
    return () => {
      removeEventListener('dragover', over)
      removeEventListener('dragleave', leave)
      removeEventListener('drop', drop)
      delete window.__nativeDrop
    }
  }, [addFiles, addPending])

  // Erkannten Text ans Eingabefeld anhängen — nicht gleich senden: man soll
  // vorher noch korrigieren können.
  const insertText = (said: string) => {
    if (!said) return
    setText((cur) => (cur.trim() ? `${cur.replace(/\s+$/, '')} ${said}` : said))
    requestAnimationFrame(() => {
      autosize()
      input.current?.focus()
    })
  }

  const showMicError = (msg: string) => {
    setMicError(msg)
    setTimeout(() => setMicError((m) => (m === msg ? '' : m)), 6000)
  }

  const toggleMic = async () => {
    if (rec.state === 'working') return
    if (rec.state === 'recording' && recording.current) {
      const r = recording.current
      recording.current = null
      setRec({ state: 'working', secs: 0 })
      try {
        insertText(await transcribe(await r.stop()))
      } catch (e) {
        showMicError(trServer((e as Error).message))
      } finally {
        setRec({ state: 'idle', secs: 0 })
      }
      return
    }
    try {
      recording.current = await startRecording()
      setRec({ state: 'recording', secs: 0 })
    } catch (e) {
      const name = (e as Error).name
      showMicError(
        name === 'NotAllowedError' || name === 'SecurityError'
          ? t(
              'Kein Zugriff aufs Mikrofon — bitte in den System- bzw. Browser-Einstellungen erlauben.',
            )
          : t('Mikrofon nicht verfügbar.'),
      )
    }
  }

  // Sekunden zählen; nach 5 Minuten von selbst beenden (Größengrenze der API).
  useEffect(() => {
    if (rec.state !== 'recording') return
    const id = setInterval(() => setRec((r) => ({ ...r, secs: r.secs + 1 })), 1000)
    return () => clearInterval(id)
  }, [rec.state])
  const toggleRef = useRef(toggleMic)
  useEffect(() => {
    toggleRef.current = toggleMic
  })
  useEffect(() => {
    if (rec.state === 'recording' && rec.secs >= 300) void toggleRef.current()
  }, [rec.state, rec.secs])
  // Esc bricht eine laufende Aufnahme ab; beim Verlassen ebenso.
  useEffect(() => {
    if (rec.state !== 'recording') return
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      recording.current?.cancel()
      recording.current = null
      setRec({ state: 'idle', secs: 0 })
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [rec.state])
  useEffect(() => () => recording.current?.cancel(), [])

  const submit = () => {
    const msg = text.trim()
    if (!msg && !pending.length) return
    if (location.pathname !== '/chat') navigate('/chat')
    setText('')
    requestAnimationFrame(autosize)
    if (msg.startsWith('/') && !pending.length) {
      runCommand(msg, {
        providers: providers.data ?? [],
        folders: folders.data ?? [],
        navigate,
        openPicker: setPicker,
      })
      return
    }
    void send(msg)
  }

  return (
    <Surface className={s.composer}>
      {!!conv?.queue.length && (
        <div className={s.queue}>
          ⏳ <b>{conv.queue.length}</b>{' '}
          {t('in Warteschlange — läuft automatisch nach der aktuellen Aufgabe (gleiche Session):')}
          {conv.queue.map((m, i) => (
            <div key={i} className={s.qitem}>
              <span>{m.text.slice(0, 90) || t('(Bild)')}</span>
              <button type="button" className={s.qx} onClick={() => removeQueued(i)}>
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      <Pickers open={picker} setOpen={setPicker} />
      {!!pending.length && (
        <div className={s.thumbs}>
          {pending.map((p, i) => (
            <div key={p.path} className={s.th}>
              {isPdf(p.url) ? (
                <span className={s.doc} title={p.name}>
                  📄 {p.name || 'PDF'}
                </span>
              ) : (
                <img src={p.url} alt="" />
              )}
              <button type="button" className={s.x} onClick={() => removePending(i)}>
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {micError && <div className={s.micError}>⚠ {micError}</div>}
      <div className={s.row}>
        {busy && (
          <button type="button" className={s.stop} title={t('Cody stoppen')} onClick={stop}>
            ⏹ STOP
          </button>
        )}
        <button
          type="button"
          className={s.attach}
          title={t('Bild anhängen')}
          onClick={() => file.current?.click()}
        >
          ⧉
        </button>
        {canRecord() && (
          <button
            type="button"
            className={`${s.attach} ${rec.state === 'recording' ? s.recording : ''}`}
            title={
              rec.state === 'recording'
                ? t('Aufnahme beenden (Esc = verwerfen)')
                : t('Spracheingabe — klicken, sprechen, nochmal klicken')
            }
            onClick={() => void toggleMic()}
          >
            {rec.state === 'working'
              ? '⏳'
              : rec.state === 'recording'
                ? `⏺ ${Math.floor(rec.secs / 60)}:${String(rec.secs % 60).padStart(2, '0')}`
                : '🎤'}
          </button>
        )}
        <textarea
          ref={input}
          className={s.input}
          rows={1}
          value={text}
          placeholder={t('> Nachricht eingeben... (Bilder: einfügen / ziehen / ⧉)')}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          onPaste={(e) => {
            const imgs = [...e.clipboardData.items]
              .filter((it) => it.type.startsWith('image/'))
              .map((it) => it.getAsFile())
              .filter((f): f is File => !!f)
            if (imgs.length) {
              e.preventDefault()
              addFiles(imgs)
            }
          }}
        />
        <button
          type="button"
          className={s.send}
          title={
            busy
              ? t(
                  'Geht SOFORT an den laufenden Cody (Steering) — er bezieht es in die aktuelle Arbeit ein',
                )
              : undefined
          }
          onClick={submit}
        >
          {busy ? t('➤ EINWERFEN') : t('SENDEN')}
        </button>
      </div>
      <div className={s.hint}>
        {t('ENTER = senden · SHIFT+ENTER = neue Zeile · 📂 Ordner · 🛡 Mode · 🧠 Modell ·')}{' '}
        <code>/help</code> {t('= Befehle')}
      </div>
      <input
        ref={file}
        type="file"
        accept="image/*,.pdf,application/pdf"
        multiple
        hidden
        onChange={(e) => {
          addFiles([...(e.target.files ?? [])])
          e.target.value = ''
        }}
      />
      {dragging && <div className={s.dropmask}>{t('⌬ BILD HIER ABLEGEN ⌬')}</div>}
    </Surface>
  )
}
