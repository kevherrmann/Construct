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
