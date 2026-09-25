import { useLayoutEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { linkifyPaths, renderMarkdown } from '@/lib/markdown'

interface Props {
  text: string
  /** Während des Streamens: blinkender Cursor, noch keine Pfad-Links. */
  streaming?: boolean
  className?: string
}

// Das HTML kommt bereinigt (DOMPurify) aus renderMarkdown. Pfad-Links und
// Kopier-Knöpfe hängen wir danach direkt ins DOM — React fasst den Inhalt von
// dangerouslySetInnerHTML nicht an, solange sich `html` nicht ändert.
export function Markdown({ text, streaming, className }: Props) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  const html = useMemo(
    () => renderMarkdown(text) + (streaming ? '<span class="caret">&nbsp;</span>' : ''),
    [text, streaming],
  )

  useLayoutEffect(() => {
    const el = ref.current
    if (!el || streaming) return
    linkifyPaths(el, t('Datei ansehen (Rechtsklick → Speichern)'))
    // Kopier-Knopf auf jedem Code-Block.
    const label = t('⧉ Kopieren')
    el.querySelectorAll('pre').forEach((pre) => {
      const code = pre.querySelector('code')
      if (!code || pre.querySelector('.copy-btn')) return
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = 'copy-btn'
      btn.textContent = label
      btn.onclick = (e) => {
        e.stopPropagation()
        navigator.clipboard.writeText(code.innerText).then(
          () => {
            btn.textContent = t('✓ Kopiert')
            btn.classList.add('done')
            setTimeout(() => {
              btn.textContent = label
              btn.classList.remove('done')
            }, 1500)
          },
          () => {
            btn.textContent = t('✗ Fehler')
            setTimeout(() => (btn.textContent = label), 1500)
          },
        )
      }
      pre.appendChild(btn)
    })
  }, [html, streaming, t])

  return <div ref={ref} className={className} dangerouslySetInnerHTML={{ __html: html }} />
}
