import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/common'
import { Marked } from 'marked'
import 'highlight.js/styles/atom-one-dark.css'

// Wie md() der alten Oberfläche: Zeilenumbrüche bleiben Umbrüche, Code wird
// mit highlight.js eingefärbt, alles läuft durch DOMPurify. Die Klasse "hljs"
// setzt die alte Fassung (marked v4) nicht — dadurch bleibt der Grundtext im
// Codeblock in der Theme-Farbe, nur die Token werden bunt.
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

export const renderMarkdown = (text: string) =>
  DOMPurify.sanitize(marked.parse(text || '', { async: false }))
