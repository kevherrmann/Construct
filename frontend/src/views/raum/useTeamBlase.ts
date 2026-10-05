import { useMemo } from 'react'
import { useAuftrag, useTeamAn, useTeamStand } from '@/api/team'
import { useLiveZug } from '../auftraege/useLiveZug'
import { lageAus, type Lage } from './lage'

/** Wer aus der Firma gerade spricht: seine Lage (wie die des Assistenten) samt
 *  Name, Farbe und Auftrag. */
export interface TeamBlase {
  slug: string
  name: string
  /** Akzentfarbe "r, g, b". */
  farbe: string
  /** Auftrags-ID (für „Verlauf"). */
  auftrag: string
  /** Zug, aus dem gelesen wird: wechselt er, ist es eine neue Blase. */
  run: string
  lage: Lage
}

// Arbeitet die Firma, spricht im Raum der, der gerade dran ist: zuerst wer an der
// Werkbank steht, sonst die Chefin (sie verteilt und prüft), sonst irgendwer. Der
// Zug wird live mitgelesen wie in der Aufträge-Ansicht — dieselben Ereignisse, aus
// denen auch die Blase des Assistenten entsteht.
export function useTeamBlase(werk: string | null): TeamBlase | null {
  const an = useTeamAn()
  const { data: stand } = useTeamStand()
  const aktiv = an ? (stand?.aktiv ?? []) : []
  const zug =
    aktiv.find((x) => x.agent === werk) ?? aktiv.find((x) => x.agent === 'chef') ?? aktiv[0]
  // Ältere Server nennen den Zug im Stand noch nicht: dann steht er im Auftrag.
  const { data: auftrag } = useAuftrag(zug && !zug.run ? zug.ticket : null)
  const run = zug?.run || auftrag?.ticket.in_arbeit?.run_id || null
  const { lauf, fertig } = useLiveZug(run)
  const lage = useMemo(() => lageAus(lauf.items, !fertig, false), [lauf, fertig])
  if (!zug || !run) return null
  return {
    slug: zug.agent,
    name: zug.name,
    farbe: zug.color,
    auftrag: zug.ticket,
    run,
    lage,
  }
}
