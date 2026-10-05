import { useEffect, useMemo, useState } from 'react'
import { useBelegschaft, useTeamAn, useTeamStand, type Agent } from '@/api/team'
import { RANDPLAETZE, SITZE, sitzFuss, type PaarId, type Platz, type Seite } from './stationen'

/** Dauer von Hin- und Rückweg (ms); muss zur Übergangszeit im CSS passen. */
export const WEG_MS = 1100
const BESUCH_BLEIBT_MS = 2200

export interface Besuch {
  slug: string
  /** 'start' = steht noch am Podest, 'hin' = geht zum Tisch, 'zurueck' = geht heim. */
  phase: 'start' | 'hin' | 'zurueck'
}

/** Ein Mitarbeiter im Raum: wo er sitzt (am Doppelschreibtisch oder am Rand). */
export interface Sitz {
  agent: Agent
  /** Fußpunkt seines Stuhls im Raum. */
  platz: Platz
  paar?: PaarId
  seite?: Seite
}

export interface BueroStand {
  leute: Sitz[]
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

  const leute = useMemo<Sitz[]>(() => {
    const aktiv = (bel?.agents ?? []).filter((a) => a.slug !== 'chef' && a.status === 'active')
    let rand = 0
    const out: Sitz[] = []
    for (const agent of aktiv) {
      const sitz = SITZE[agent.slug]
      if (sitz)
        out.push({
          agent,
          paar: sitz.paar,
          seite: sitz.seite,
          platz: sitzFuss(sitz.paar, sitz.seite),
        })
      else if (rand < RANDPLAETZE.length) out.push({ agent, platz: RANDPLAETZE[rand++]! })
    }
    return out
  }, [bel])
  const arbeiten = useMemo(
    () =>
      new Set(
        (stand?.aktiv ?? [])
          .map((x) => x.agent)
          .filter((slug) => leute.some((l) => l.agent.slug === slug)),
      ),
    [stand, leute],
  )

  // Wer an der Werkbank steht, bleibt dort, bis er fertig ist: sonst liefen zwei
  // gleichzeitig Arbeitende ständig hin und her. Nur wer ein Bild an der Werkbank
  // hat (die Fest-Besetzten), geht dorthin. (Zustand beim Zeichnen angepasst statt
  // im Effekt: so gibt es keinen Zeichendurchgang mit dem alten Wert.)
  const [werk, setWerk] = useState<string | null>(null)
  const kannHin = (slug: string) => !!SITZE[slug]
  const gewuenscht = !werkFrei
    ? null
    : werk && arbeiten.has(werk)
      ? werk
      : ([...arbeiten].find(kannHin) ?? null)
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

  if (!an || !leute.length) return null
  return { leute, arbeiten, werk, besuch }
}
