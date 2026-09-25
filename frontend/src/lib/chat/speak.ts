/** Vorlesbarer Text einer Antwort: Markdown genügt, der Server entfernt Code und Formatierung. */
export function speakableText(blocks: { t: string; text?: string }[]): string {
  return blocks
    .filter((b) => b.t === 'text' && b.text)
    .map((b) => b.text)
    .join('\n')
    .trim()
}
