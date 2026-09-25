/** Kurzfassung eines Werkzeugaufrufs für die Kopfzeile der Tool-Box. */
export function toolSummary(input: unknown): string {
  if (!input || typeof input !== 'object') return ''
  const i = input as Record<string, unknown>
  const f =
    i.command ?? i.file_path ?? i.path ?? i.pattern ?? i.url ?? i.query ?? i.prompt ?? i.description
  if (f) return String(f).replace(/\s+/g, ' ').slice(0, 90)
  const k = Object.keys(i)[0]
  return k ? `${k}: ${String(i[k]).slice(0, 70)}` : ''
}
