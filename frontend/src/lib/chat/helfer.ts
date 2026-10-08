import type { Helfer, HelferStand, StreamEvent } from './types'

// Welche Helfer (Agent/Task) arbeiten gerade? Aus denselben Stream-Ereignissen
// abgeleitet wie die Sprechblasen, ohne UI: der Raum zeigt sie als Hologramme.
// Rein funktional und ohne Veränderung der Eingabe — ändert ein Ereignis nichts,
// kommt dieselbe Liste zurück (der Raum zeichnet dann nicht neu).

export const helferOffen = (h: Helfer) => h.stand === 'start' || h.stand === 'laeuft'

export interface HelferUmfeld {
  /** Sprechblase, die gerade läuft: dort hängt ein neuer Helfer. */
  antwort: string
  /** Zug fertig, Prozess wartet auf Hintergrundaufgaben (Ereignis `nachlauf`). */
  nachlauf: boolean
}

function aendern(liste: Helfer[], id: string | undefined, f: (h: Helfer) => Helfer): Helfer[] {
  const i = id ? liste.findIndex((h) => h.id === id) : -1
  if (i < 0) return liste
  const neu = f(liste[i]!)
  return neu === liste[i] ? liste : liste.map((h, j) => (j === i ? neu : h))
}

/** Alle offenen Helfer (oder nur die, auf die `nur` zutrifft) auf `stand` setzen. */
function schliessen(
  liste: Helfer[],
  stand: HelferStand,
  nur: (h: Helfer) => boolean = () => true,
): Helfer[] {
  if (!liste.some((h) => helferOffen(h) && nur(h))) return liste
  return liste.map((h) => (helferOffen(h) && nur(h) ? { ...h, stand } : h))
}

export function helferNach(liste: Helfer[], ev: StreamEvent, u: HelferUmfeld): Helfer[] {
  switch (ev.type) {
    case 'helfer': {
      if (ev.stand === 'start') {
        if (liste.some((h) => h.id === ev.id)) return liste // Replay nach Reconnect
        return [
          ...liste,
          {
            id: ev.id,
            antwort: u.antwort,
            beschreibung: ev.beschreibung ?? '',
            typ: ev.typ ?? '',
            stand: 'start',
            werkzeug: ev.werkzeug ?? '',
            detail: ev.detail ?? '',
            hintergrund: !!ev.hintergrund,
          },
        ]
      }
      // Fortschritt oder Ende eines Helfers, dessen Start wir nicht kennen: nichts
      // zeigen — ein Hologramm, das nur zerfällt, wäre falscher als keins.
      return aendern(liste, ev.id, (h) =>
        helferOffen(h)
          ? {
              ...h,
              stand: ev.stand,
              werkzeug: ev.werkzeug || h.werkzeug,
              detail: ev.detail || h.detail,
            }
          : h,
      )
    }
    case 'tool':
      // Die eigenen Schritte des Helfers kommen oft vor seinem Fortschritt an.
      return aendern(liste, ev.parent, (h) =>
        helferOffen(h) && h.werkzeug !== ev.name ? { ...h, stand: 'laeuft', werkzeug: ev.name } : h,
      )
    case 'done':
      // Ein Helfer im Vordergrund endet spätestens mit seinem Zug. Einer im
      // Hintergrund lebt im Nachlauf weiter — ohne Nachlauf stirbt er mit dem Prozess.
      return u.nachlauf
        ? schliessen(liste, 'fertig', (h) => !h.hintergrund)
        : schliessen(liste, 'fertig')
    case 'nachlauf_ende':
    case 'closed':
      // Spätestens hier ist der Prozess weg. Auch ein nach einem Neustart
      // nachgelesener Lauf endet so, und der kennt keine Helfer-Ereignisse.
      return schliessen(liste, 'fertig')
    case 'error':
      return schliessen(liste, 'fehler')
    default:
      return liste
  }
}
