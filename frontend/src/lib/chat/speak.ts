/** Vorlesbarer Text einer Antwort: Markdown genügt, der Server entfernt Code und Formatierung. */
export function speakableText(blocks: { t: string; text?: string }[]): string {
  return blocks
    .filter((b) => b.t === 'text' && b.text)
    .map((b) => b.text)
    .join('\n')
    .replace(/\n*[ \t]*\[\[[^\n]*$/, '') // Ticket-Marker (lib/chat/marken.ts) wird nicht vorgelesen
    .trim()
}
