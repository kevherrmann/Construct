import type { StreamEvent } from './types'

// Zerlegt einen SSE-Datenstrom in Events. Pakete kommen beliebig zerstückelt an
// (TCP), darum wird bis zur Leerzeile gepuffert. Nur "data: "-Zeilen zählen;
// kaputtes JSON wird übersprungen statt den Lauf abzubrechen.
export class SseParser {
  private buf = ''

  push(chunk: string): StreamEvent[] {
    this.buf += chunk
    const out: StreamEvent[] = []
    let i: number
    while ((i = this.buf.indexOf('\n\n')) >= 0) {
      const frame = this.buf.slice(0, i)
      this.buf = this.buf.slice(i + 2)
      if (!frame.startsWith('data: ')) continue
      try {
        out.push(JSON.parse(frame.slice(6)) as StreamEvent)
      } catch {
        /* unvollständig oder kaputt — überspringen */
      }
    }
    return out
  }
}
