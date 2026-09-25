import { useEffect, useRef, type MouseEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { renderMarkdown } from './renderMarkdown'
import s from './Markdown.module.css'

declare global {
  interface Window {
    pywebview?: { api?: { open_url?: (url: string) => void } }
  }
}

// Externe Links gehören in den Systembrowser, nicht in dieses Fenster.
// Die WebView (desktop.py) hat weder Adress- noch Zurück-Leiste: ein Klick auf
// einen Link navigiert das GANZE Fenster dorthin, und es gibt keinen Weg
// zurück zur App. Im Browser ist ein neuer Tab ebenfalls richtig.
function onLinkClick(e: MouseEvent<HTMLDivElement>) {
  if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return
  const a = (e.target as HTMLElement).closest?.('a[href]') as HTMLAnchorElement | null
  if (!a) return
  let u: URL
  try {
    u = new URL(a.href, location.href)
  } catch {
    return
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return // mailto:, #anker, blob:
  if (u.origin === location.origin) return // eigene Seite normal lassen
  e.preventDefault()
  const api = window.pywebview?.api
  if (api?.open_url)
    api.open_url(u.href) // Fenster → Systembrowser
  else window.open(u.href, '_blank', 'noopener') // Browser → neuer Tab
}

/** Bereinigtes Markdown in einer Chat-Blase, mit Kopier-Knopf an jedem Codeblock. */
export function MarkdownBubble({ text }: { text: string }) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  const html = renderMarkdown(text)

  // Copy-Button auf jeden Code-Block (<pre>) — nachträglich ins fertige HTML,
  // weil das Markdown als Ganzes gesetzt wird.
  useEffect(() => {
    const timers: number[] = []
    ref.current?.querySelectorAll('pre').forEach((pre) => {
      const code = pre.querySelector('code')
      if (!code || pre.querySelector('button')) return
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = s.copy!
      const idle = t('⧉ Kopieren')
      btn.textContent = idle
      const reset = () =>
        timers.push(
          window.setTimeout(() => {
            btn.textContent = idle
            btn.classList.remove(s.done!)
          }, 1500),
        )
      btn.onclick = (ev) => {
        ev.stopPropagation()
        navigator.clipboard.writeText(code.innerText).then(
          () => {
            btn.textContent = t('✓ Kopiert')
            btn.classList.add(s.done!)
            reset()
          },
          () => {
            btn.textContent = t('✗ Fehler')
            reset()
          },
        )
      }
      pre.appendChild(btn)
    })
    return () => timers.forEach(clearTimeout)
  }, [html, t])

  return (
    <div className={s.msg}>
      <div
        ref={ref}
        className={s.bubble}
        onClick={onLinkClick}
        // Durch DOMPurify bereinigt (renderMarkdown).
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  )
}
