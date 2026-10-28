import { ohneUi } from './genui'

/** Vorlesbarer Text einer Antwort: Markdown genügt, der Server entfernt Code und Formatierung.
 *  Bausteine (genui.ts) fallen ganz weg — sonst hieße es „Codeblock ausgelassen“. */
export function speakableText(blocks: { t: string; text?: string }[]): string {
  return ohneUi(
    blocks
      .filter((b) => b.t === 'text' && b.text)
      .map((b) => b.text)
      .join('\n'),
  )
    .replace(/\n*[ \t]*\[\[[^\n]*$/, '') // Ticket-Marker (lib/chat/marken.ts) wird nicht vorgelesen
    .trim()
}
