import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Person } from '@/api/team'
import { BlockView } from '@/components/chat/Message'
import { applyEvent, initialRun, type RunState } from '@/lib/chat/reducer'
import { SseParser } from '@/lib/chat/sse'
import { Avatar } from '../personal/Person'
import s from './Auftraege.module.css'

/** Der laufende Zug einer Person — dieselbe Darstellung wie im Chat (Text,
 *  Werkzeugkarten, Ergebnisse), ohne dessen Sitzungsverwaltung. Der Server
 *  spielt beim Verbinden alles bisher Passierte nach: man steigt mittendrin ein
 *  und sieht trotzdem den ganzen Zug. */
export function LiveZug({ runId, person }: { runId: string; person: Person }) {
  const { t } = useTranslation()
  const [lauf, setLauf] = useState<RunState>(initialRun)
  const [weg, setWeg] = useState(false)
  useEffect(() => {
    const ctrl = new AbortController()
    ;(async () => {
      // Der Server spielt beim Verbinden alles bisher Passierte nach — ein Abriss (Netz,
      // Schlaf, Proxy) heilt also durch Neuverbinden, genau wie im Chat. Ohne das
      // bliebe die Anzeige für immer auf "arbeitet gerade" stehen.
      for (let versuch = 0; versuch < 40 && !ctrl.signal.aborted; versuch++) {
        let rs = initialRun()
        let zu = false
        try {
          const res = await fetch(`/api/stream/${encodeURIComponent(runId)}`, {
            signal: ctrl.signal,
          })
          if (!res.ok) {
            setWeg(true)
            return
          }
          setWeg(false)
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
            if (neu) setLauf(rs)
            if (zu) return
          }
        } catch {
          if (ctrl.signal.aborted) return
        }
        await new Promise((r) => setTimeout(r, 1500))
      }
    })()
    return () => ctrl.abort()
  }, [runId])

  if (weg)
    return (
      <div className={s.notiz}>
        ⚠ {t('Der Zug ist nicht mehr abrufbar — er ist fertig und weggeräumt.')}
      </div>
    )
  return (
    <div className={s.zeile} style={{ ['--accent-rgb' as string]: person.color }}>
      <Avatar p={person} groesse={32} aktiv />
      <div className={s.col}>
        <div className={s.who}>
          {person.name.toUpperCase()} · {t('arbeitet gerade')}
        </div>
        <div className={s.bubble}>
          {lauf.items.map((it) =>
            it.kind === 'bot'
              ? it.blocks.map((b, i) => <BlockView key={`${it.id}:${i}`} block={b} />)
              : null,
          )}
        </div>
      </div>
    </div>
  )
}
