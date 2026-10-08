import { useMemo } from 'react'
import { useAuftrag, useTeamAn, useTeamStand } from '@/api/team'
import { useLiveZug } from '@/components/firma/useLiveZug'
import type { Helfer } from '@/lib/chat/types'
import { lageAus, type Lage } from './lage'

/** Wer aus der Firma gerade spricht: seine Lage (wie die des Assistenten) samt
 *  Name, Farbe und Auftrag. */
export interface TeamBlase {
  slug: string
  name: string
  /** Akzentfarbe "r, g, b". */
  farbe: string
  /** Auftrags-ID. */
  auftrag: string
  /** Chat-Session des Auftrags: dort schreibt die Firma („Verlauf“ springt hin). */
  session: string
  /** Zug, aus dem gelesen wird: wechselt er, ist es eine neue Blase. */
  run: string
  lage: Lage
}

/** Der Zug der Chefin, solange sie für die Firma arbeitet (sonst null). Die Figur
 *  am Podest folgt ihm; er wird vor dem Büro gebraucht, die Blase erst danach. */
export interface ChefZug {
  run: string
  lage: Lage
  /** Ihre Helfer: stehen als Hologramme neben der Figur am Podest. */
  helfer: Helfer[]
}

const useZugLage = (run: string | null) => useZug(run).lage

function useZug(run: string | null) {
  const { lauf, fertig } = useLiveZug(run)
  const lage = useMemo(() => lageAus(lauf.items, !fertig, false), [lauf, fertig])
  return { lage, helfer: lauf.helfer }
}

export function useChefZug(): ChefZug | null {
  const an = useTeamAn()
  const { data: stand } = useTeamStand()
  const run = (an && stand?.aktiv.find((x) => x.agent === 'chef')?.run) || null
  const { lage, helfer } = useZug(run)
  return run ? { run, lage, helfer } : null
}

// Arbeitet die Firma, spricht im Raum der, der gerade dran ist: zuerst wer an der
// Werkbank steht, sonst die Chefin (sie verteilt und prüft), sonst irgendwer. Der
// Zug wird live mitgelesen wie im Chat — dieselben Ereignisse, aus
// denen auch die Blase des Assistenten entsteht. Den der Chefin liest useChefZug
// schon mit: dann nicht ein zweites Mal.
export function useTeamBlase(werk: string | null, chef: ChefZug | null): TeamBlase | null {
  const an = useTeamAn()
  const { data: stand } = useTeamStand()
  const aktiv = an ? (stand?.aktiv ?? []) : []
  const zug =
    aktiv.find((x) => x.agent === werk) ?? aktiv.find((x) => x.agent === 'chef') ?? aktiv[0]
  // Ältere Server nennen den Zug im Stand noch nicht: dann steht er im Auftrag.
  const { data: auftrag } = useAuftrag(zug && !zug.run ? zug.ticket : null)
  const run = zug?.run || auftrag?.ticket.in_arbeit?.run_id || null
  const vomChef = !!chef && chef.run === run
  const eigene = useZugLage(vomChef ? null : run)
  if (!zug || !run) return null
  return {
    slug: zug.agent,
    name: zug.name,
    farbe: zug.color,
    auftrag: zug.ticket,
    session: zug.session ?? '',
    run,
    lage: vomChef ? chef.lage : eigene,
  }
}
