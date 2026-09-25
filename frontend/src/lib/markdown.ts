import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/common'
import { Marked } from 'marked'
import 'highlight.js/styles/atom-one-dark.css'

// Markdown → bereinigtes HTML, wie md() der alten Oberfläche: Zeilenumbrüche
// bleiben Umbrüche, Code wird mit highlight.js eingefärbt, alles läuft durch
// DOMPurify. Jetzt lokal gebündelt statt vom CDN — Antworten erscheinen auch
// offline. Die Klasse "hljs" setzte die alte Fassung (marked v4) nicht; ohne
// sie bleibt der Grundtext im Codeblock in der Theme-Farbe, nur die Token
// werden bunt.
const marked = new Marked({
  breaks: true,
  renderer: {
    code({ text, lang }) {
      const l = (lang ?? '').match(/^\S*/)?.[0] ?? ''
      const language = hljs.getLanguage(l) ? l : 'plaintext'
      let html: string
      try {
        html = hljs.highlight(text, { language }).value
      } catch {
        html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      }
      return `<pre><code class="language-${language}">${html}</code></pre>\n`
    },
  },
})

export function renderMarkdown(text: string): string {
  return DOMPurify.sanitize(marked.parse(text || '', { async: false }))
}

// Absolute Pfade in Antworten anklickbar machen (Vorschau/Download über /api/file).
const PATH_RE = /(^|[\s('"„`>])(\/(?:home|Users)\/[\w.\-/]+\.\w{1,8})/g

export function linkifyPaths(root: HTMLElement, title: string) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) =>
      n.parentElement?.closest('a') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  })
  const nodes: Text[] = []
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    PATH_RE.lastIndex = 0
    if (PATH_RE.test(n.nodeValue ?? '')) nodes.push(n as Text)
  }
  for (const node of nodes) {
    const s = node.nodeValue ?? ''
    const frag = document.createDocumentFragment()
    let last = 0
    PATH_RE.lastIndex = 0
    for (let m = PATH_RE.exec(s); m; m = PATH_RE.exec(s)) {
      frag.appendChild(document.createTextNode(s.slice(last, m.index) + m[1]))
      const a = document.createElement('a')
      a.href = `/api/file?path=${encodeURIComponent(m[2]!)}`
      a.target = '_blank'
      a.rel = 'noopener'
      a.textContent = m[2]!
      a.title = title
      frag.appendChild(a)
      last = m.index + m[0].length
    }
    frag.appendChild(document.createTextNode(s.slice(last)))
    node.parentNode?.replaceChild(frag, node)
  }
}
