import { useEffect, useRef } from 'react'
import {
  codyTippt,
  eintauchen,
  klangAktiv,
  klangEinstellen,
  oeffnen,
  schliessen,
  streifen,
  uhr,
} from '@/lib/klang'
import { useSettings } from '@/stores/settings'
import type { Ansicht, StationId } from './stationen'

/** Klänge des Raums: was gerade passiert → lib/klang.ts. */
export function useRaumKlang({
  ansicht,
  fokus,
  tauchen,
  amWerk,
}: {
  ansicht: Ansicht | null
  fokus: StationId | null
  tauchen: 'rein' | 'raus' | null
  amWerk: boolean
}) {
  const sound = useSettings((st) => st.settings.sound)

  useEffect(() => {
    klangAktiv(true)
    return () => {
      klangAktiv(false)
      uhr(false)
      codyTippt(false)
    }
  }, [])

  useEffect(() => {
    klangEinstellen(sound)
  }, [sound])

  // Öffnen und Schließen: Wechsel zwischen zwei Ansichten klingt wie Öffnen.
  const vorher = useRef(ansicht)
  useEffect(() => {
    const alt = vorher.current
    vorher.current = ansicht
    if (ansicht && ansicht !== alt) oeffnen()
    else if (!ansicht && alt && tauchen !== 'rein') schliessen()
  }, [ansicht, tauchen])

  useEffect(() => {
    if (tauchen === 'rein') eintauchen()
  }, [tauchen])

  useEffect(() => {
    if (fokus && !ansicht) streifen()
  }, [fokus, ansicht])

  useEffect(() => {
    uhr(ansicht === 'uhr' && sound.effekte)
    return () => uhr(false)
  }, [ansicht, sound.effekte])

  useEffect(() => {
    codyTippt(amWerk && sound.effekte)
    return () => codyTippt(false)
  }, [amWerk, sound.effekte])
}
