import { useEffect, useState } from 'react'
import { applyEvent, initialRun, type RunState } from '@/lib/chat/reducer'
import { SseParser } from '@/lib/chat/sse'

/** Der laufende Zug einer Person, live mitgelesen (Aufträge-Ansicht, Sprechblase im
 *  Raum). Der Server spielt beim Verbinden alles bisher Passierte nach: man steigt
 *  mittendrin ein und hat trotzdem den ganzen Zug. `fertig` = der Zug ist zu Ende,
 *  `weg` = er ist nicht mehr abrufbar. Ohne `runId` passiert nichts. */
interface Stand {
  run: string
  lauf: RunState
  weg: boolean
  fertig: boolean
}
const LEER: Omit<Stand, 'run'> = { lauf: initialRun(), weg: false, fertig: false }

export function useLiveZug(runId: string | null | undefined) {
  // Der Stand gehört zu einem Zug: wechselt die ID, gilt er nicht mehr.
  const [stand, setStand] = useState<Stand | null>(null)
  useEffect(() => {
    if (!runId) return
    const setze = (x: Partial<Omit<Stand, 'run'>>) =>
      setStand((v) => ({ ...(v?.run === runId ? v : { ...LEER, run: runId }), ...x }))
    const ctrl = new AbortController()
    ;(async () => {
      // Ein Abriss (Netz, Schlaf, Proxy) heilt durch Neuverbinden, genau wie im
      // Chat. Ohne das bliebe die Anzeige für immer auf "arbeitet gerade" stehen.
      for (let versuch = 0; versuch < 40 && !ctrl.signal.aborted; versuch++) {
        let rs = initialRun()
        let zu = false
        try {
          const res = await fetch(`/api/stream/${encodeURIComponent(runId)}`, {
            signal: ctrl.signal,
          })
          if (!res.ok) {
            setze({ weg: true })
            return
          }
          setze({ weg: false })
          const reader = res.body!.getReader()
          const dec = new TextDecoder()
          const parser = new SseParser()
          for (;;) {
            const { value, done } = await reader.read()
            if (done) break
            let neu = false
            for (const ev of parser.push(dec.decode(value, { stream: true }))) {
              rs = applyEvent(rs, ev)
              neu = true
              if (ev.type === 'closed' || ev.type === 'done' || ev.type === 'error') zu = true
            }
            if (neu) setze({ lauf: rs })
            if (zu) {
              setze({ fertig: true })
              return
            }
          }
        } catch {
          if (ctrl.signal.aborted) return
        }
        await new Promise((r) => setTimeout(r, 1500))
      }
    })()
    return () => ctrl.abort()
  }, [runId])
  return stand && stand.run === runId ? stand : LEER
}
