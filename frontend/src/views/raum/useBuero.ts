import { useEffect, useMemo, useState } from 'react'
import { useBelegschaft, useTeamAn, useTeamStand, type Agent } from '@/api/team'
import { PLAETZE, type Platz } from './stationen'

/** Dauer von Hin- und Rückweg (ms); muss zur Übergangszeit im CSS passen. */
const WEG_MS = 1100
const BESUCH_BLEIBT_MS = 2200

export interface Besuch {
  slug: string
  /** 'start' = steht noch am Podest, 'hin' = geht zum Tisch, 'zurueck' = geht heim. */
  phase: 'start' | 'hin' | 'zurueck'
}

export interface Arbeitsplatz {
  agent: Agent
  platz: Platz
}

export interface BueroStand {
  plaetze: Arbeitsplatz[]
  /** Wer gerade arbeitet (Slugs, ohne die Chefin). */
  arbeiten: ReadonlySet<string>
  /** Wer an der Werkbank steht (höchstens einer: es gibt dort einen Platz). */
  werk: string | null
  besuch: Besuch | null
}

/** Alles, was das Büro braucht: Belegschaft, wer arbeitet, wer an der Werkbank steht
 *  und bei wem die Chefin gerade vorbeischaut. `werkFrei` = der Assistent selbst steht
 *  nicht an der Werkbank. */
export function useBuero(werkFrei: boolean): BueroStand | null {
  const an = useTeamAn()
  const { data: bel } = useBelegschaft()
  const { data: stand } = useTeamStand()

  const plaetze = useMemo<Arbeitsplatz[]>(
    () =>
      (bel?.agents ?? [])
        .filter((a) => a.slug !== 'chef' && a.status === 'active')
        .slice(0, PLAETZE.length)
        .map((agent, i) => ({ agent, platz: PLAETZE[i]! })),
    [bel],
  )
  const arbeiten = useMemo(
    () =>
      new Set(
        (stand?.aktiv ?? [])
          .map((x) => x.agent)
          .filter((slug) => plaetze.some((p) => p.agent.slug === slug)),
      ),
    [stand, plaetze],
  )

  // Wer an der Werkbank steht, bleibt dort, bis er fertig ist: sonst liefen zwei
  // gleichzeitig Arbeitende ständig hin und her. (Zustand beim Zeichnen angepasst
  // statt im Effekt: so gibt es keinen Zeichendurchgang mit dem alten Wert.)
  const [werk, setWerk] = useState<string | null>(null)
  const gewuenscht = !werkFrei
    ? null
    : werk && arbeiten.has(werk)
      ? werk
      : ([...arbeiten][0] ?? null)
  if (gewuenscht !== werk) setWerk(gewuenscht)

  // Wer neu dazukommt, wird von der Chefin besucht (nicht beim ersten Laden und
  // nicht, solange schon ein Besuch läuft).
  const [besuch, setBesuch] = useState<Besuch | null>(null)
  const [gesehen, setGesehen] = useState<string | null>(null)
  const schluessel = [...arbeiten].sort().join(',')
  if (schluessel !== gesehen) {
    const frueher = new Set((gesehen ?? '').split(',').filter(Boolean))
    setGesehen(schluessel)
    const neu = gesehen === null ? undefined : [...arbeiten].find((slug) => !frueher.has(slug))
    if (neu && !besuch) setBesuch({ slug: neu, phase: 'start' })
  }
  useEffect(() => {
    if (!besuch) return
    const weiter: Record<Besuch['phase'], [number, Besuch | null]> = {
      start: [40, { ...besuch, phase: 'hin' }],
      hin: [WEG_MS + BESUCH_BLEIBT_MS, { ...besuch, phase: 'zurueck' }],
      zurueck: [WEG_MS, null],
    }
    const [warte, danach] = weiter[besuch.phase]
    const id = setTimeout(() => setBesuch(danach), warte)
    return () => clearTimeout(id)
  }, [besuch])

  if (!an || !plaetze.length) return null
  return { plaetze, arbeiten, werk, besuch }
}
