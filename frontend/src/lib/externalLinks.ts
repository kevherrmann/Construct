// Externe Links gehören in den Browser, in dem man sonst arbeitet — nicht in
// dieses Fenster, sonst ist der Chat weg. Im eigenen App-Fenster (desktop.py
// öffnet es mit ?fenster=1, eigenes Browser-Profil) öffnet sie der Server im
// Standardbrowser; in einem normalen Tab reicht ein neuer Tab.
// Bewusst ein globaler Handler statt target="_blank" beim Rendern: so sind auch
// alle gestreamten Markdown-Links erfasst.

// Beim Laden festhalten: der Router leitet / auf /chat um und wirft die Query
// weg. sessionStorage gilt genau für dieses Fenster.
function merken() {
  try {
    if (new URLSearchParams(location.search).get('fenster') === '1')
      sessionStorage.setItem('mxfenster', '1')
  } catch {
    /* ohne Speicher: dann eben neue Tabs */
  }
}
merken()
const imFenster = () => {
  try {
    return sessionStorage.getItem('mxfenster') === '1'
  } catch {
    return false
  }
}

async function imStandardbrowser(url: string): Promise<boolean> {
  try {
    const r = await fetch('/api/open-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
    return r.ok && !!((await r.json()) as { ok?: boolean }).ok
  } catch {
    return false
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
      if (!imFenster()) {
        window.open(u.href, '_blank', 'noopener')
        return
      }
      void imStandardbrowser(u.href).then((ok) => ok || window.open(u.href, '_blank', 'noopener'))
    },
    true,
  )
}
