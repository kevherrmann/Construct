import { canDictate, startDictation, type Dictation } from '@/lib/dictation'
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
  // Spracheingabe: Diktat läuft (Sekunden) bzw. der Rest kommt noch nach.
  const [rec, setRec] = useState<{ state: 'idle' | 'recording' | 'working'; secs: number }>({
    state: 'idle',
    secs: 0,
  })
  const [micError, setMicError] = useState('')
  const dictation = useRef<Dictation | null>(null)
  // Eingabetext vor dem Diktat — das Gesprochene wird dahinter geschrieben.
  const base = useRef('')
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

  // Das Gesprochene erscheint schon während des Sprechens im Eingabefeld,
  // hinter dem, was vorher drinstand. Gesendet wird nicht — man soll noch
  // korrigieren können.
  const withSpoken = (spoken: string) => {
    const before = base.current
    if (!spoken) return before
    return before.trim() ? `${before.replace(/\s+$/, '')} ${spoken}` : spoken
  }
  const showSpoken = (spoken: string) => {
    setText(withSpoken(spoken))
    requestAnimationFrame(() => {
      const el = input.current
      if (el) el.scrollTop = el.scrollHeight
    })
  }

  const showMicError = (msg: string) => {
    setMicError(msg)
    setTimeout(() => setMicError((m) => (m === msg ? '' : m)), 6000)
  }

  const toggleMic = async () => {
    if (rec.state === 'working') return
    if (rec.state === 'recording' && dictation.current) {
      const d = dictation.current
      dictation.current = null
      setRec({ state: 'working', secs: 0 })
      showSpoken(await d.stop())
      setRec({ state: 'idle', secs: 0 })
      requestAnimationFrame(() => input.current?.focus())
      return
    }
    base.current = text
    try {
      dictation.current = await startDictation({
        onText: showSpoken,
        onError: (msg) => {
          dictation.current = null
          setRec({ state: 'idle', secs: 0 })
          showMicError(trServer(msg))
        },
      })
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
  const cancelMic = () => {
    dictation.current?.cancel()
    dictation.current = null
    setText(base.current)
    setRec({ state: 'idle', secs: 0 })
  }

  // Sekunden zählen; kurz vor dem 10-Minuten-Limit der Live-API von selbst
  // beenden.
  useEffect(() => {
    if (rec.state !== 'recording') return
    const id = setInterval(() => setRec((r) => ({ ...r, secs: r.secs + 1 })), 1000)
    return () => clearInterval(id)
  }, [rec.state])
  const toggleRef = useRef(toggleMic)
  const cancelRef = useRef(cancelMic)
  useEffect(() => {
    toggleRef.current = toggleMic
    cancelRef.current = cancelMic
  })
  useEffect(() => {
    if (rec.state === 'recording' && rec.secs >= 570) void toggleRef.current()
  }, [rec.state, rec.secs])
  // Esc verwirft ein laufendes Diktat (das Eingabefeld ist wie vorher);
  // beim Verlassen ebenso.
  useEffect(() => {
    if (rec.state !== 'recording') return
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cancelRef.current()
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [rec.state])
  useEffect(() => () => dictation.current?.cancel(), [])

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
        {canDictate() && (
          <button
            type="button"
            className={`${s.attach} ${rec.state === 'recording' ? s.recording : ''}`}
            title={
              rec.state === 'recording'
                ? t('Diktat beenden (Enter) · Esc = verwerfen')
                : t('Spracheingabe — klicken und sprechen, der Text erscheint gleich im Feld')
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
          readOnly={rec.state !== 'idle'}
          placeholder={t('> Nachricht eingeben... (Bilder: einfügen / ziehen / ⧉)')}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              // Während des Diktats beendet Enter nur das Diktat — gesendet
              // wird erst mit dem nächsten Enter, nach einem Blick auf den Text.
              if (rec.state === 'recording') void toggleMic()
              else if (rec.state === 'idle') submit()
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
              return
            }
            // WebKitGTK (Desktop-Fenster) reicht kopierte Bilder nicht durch —
            // dann holt desktop.py sie direkt aus der Zwischenablage. Nur wenn
            // kein Text drin ist: Zellen aus Calc & Co. liegen zusätzlich als
            // Bild in der Ablage, da soll der Text kommen, kein Anhang.
            const api = window.pywebview?.api
            if (api?.paste_image && !e.clipboardData.types.includes('text/plain')) {
              e.preventDefault()
              void api.paste_image().then((a) => a && addPending(a))
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
