import { renderMarkdown } from '@/lib/markdown'

describe('renderMarkdown', () => {
  it('färbt Code ein, ohne die hljs-Grundklasse zu setzen', () => {
    const html = renderMarkdown('```python\ndef f():\n    return 1\n```')
    expect(html).toContain('<code class="language-python">')
    expect(html).toContain('<span class="hljs-keyword">def</span>')
  })

  it('fällt bei unbekannter Sprache auf Klartext zurück und escaped', () => {
    const html = renderMarkdown('```quatsch\n<b>x</b>\n```')
    expect(html).toContain('language-plaintext')
    expect(html).toContain('&lt;b&gt;x&lt;/b&gt;')
  })

  it('übernimmt Zeilenumbrüche und entfernt Gefährliches', () => {
    const html = renderMarkdown('a\nb <img src=x onerror="alert(1)"><script>alert(2)</script>')
    expect(html).toContain('a<br>b')
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('<script')
  })
})
