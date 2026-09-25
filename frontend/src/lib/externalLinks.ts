// Externe Links gehören in den Systembrowser, nicht in dieses Fenster. Die
// WebView (desktop.py) hat weder Adress- noch Zurück-Leiste: ein Klick auf einen
// Chat-Link navigierte das GANZE Fenster dorthin, ohne Weg zurück zur App. Im
// Browser ist ein neuer Tab ebenfalls richtig, sonst ist der Chat weg.
// Bewusst ein globaler Handler statt target="_blank" beim Rendern: so sind auch
// alle gestreamten Markdown-Links erfasst.

interface PyWebview {
  api?: { open_url?: (url: string) => void }
  platform?: string
}
declare global {
  interface Window {
    pywebview?: PyWebview
  }
}

export function installExternalLinkHandler() {
  addEventListener(
    'click',
    (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return
      const a = (e.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
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
      if (api?.open_url) api.open_url(u.href)
      else window.open(u.href, '_blank', 'noopener')
    },
    true,
  )
}
