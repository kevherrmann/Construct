import { useEffect, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import {
  gesehen,
  merkeGesehen,
  useTeamChat,
  useTeamStand,
  useUebergaben,
  type Person,
} from '@/api/team'
import { Eskalation } from './Eskalation'
import { UebergabeHinweis } from './Uebergabe'
import { LiveZug } from './LiveZug'
import { NachrichtKarte } from './NachrichtKarte'
import s from './Firma.module.css'

const GRAU: Person = { name: '?', title: '', color: '126,231,135', avatar: '' }

/** Eine Zeile der Firma im Chat, einsortiert nach ihrer Zeit (ms). */
export interface FirmaZeile {
  ts: number
  key: string
  node: ReactNode
}

/** Was die Firma in dieser Session geschrieben hat, als Zeilen zum Einsortieren
 *  zwischen die eigenen Nachrichten — dazu, was ans Ende gehört, weil es JETZT
 *  passiert: der laufende Zug und eine Rückfrage mit Antwortfeld.
 *
 *  Den Auftrag selbst (Nutzer → Geschäftsführung) zeigt der Chat nicht noch einmal:
 *  das ist die Antwort des Assistenten direkt darüber. An seiner Stelle steht eine
 *  Linie mit dem Titel, wie ein Kapitel. */
export function useFirmaImChat(sid: string | null | undefined): {
  zeilen: FirmaZeile[]
  schluss: ReactNode
} {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data } = useTeamChat(sid)
  const { data: stand } = useTeamStand()
  const { data: uebergaben } = useUebergaben(sid)
  const auftraege = data?.auftraege ?? []
  const leute = data?.agents ?? {}

  // Was hier steht, ist gelesen: die Firmenleiste und der Raum melden es nicht mehr.
  const stempel = auftraege.map((a) => `${a.id}:${a.verlauf.length}`).join(',')
  useEffect(() => {
    let neu = false
    for (const a of data?.auftraege ?? [])
      if (gesehen(a.id) !== a.verlauf.length) {
        merkeGesehen(a.id, a.verlauf.length)
        neu = true
      }
    if (neu) void qc.invalidateQueries({ queryKey: ['team', 'auftraege'] })
    // stempel fasst zusammen, was sich an den Daten ändern kann
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stempel, qc])

  const zeilen: FirmaZeile[] = []
  for (const a of auftraege)
    for (const e of a.verlauf) {
      const ts = e.ts * 1000
      if (e.von === 'kevin' && e.art === 'auftrag')
        zeilen.push({
          ts,
          key: e.id,
          node: (
            <div className={s.trenner}>
              🏢 {t('An die Firma')}: {a.titel}
              {a.board ? ` · T-${a.board}` : ''}
            </div>
          ),
        })
      else zeilen.push({ ts, key: e.id, node: <NachrichtKarte e={e} leute={leute} /> })
    }
  // Übergaben, die bei ausgeschaltetem Team-Modus liegen blieben. Ihre Zeit ist das
  // Ende des Zugs: so stehen sie direkt unter der Antwort, die sie ausgelöst hat.
  for (const u of uebergaben ?? [])
    zeilen.push({
      ts: u.erstellt * 1000,
      key: `uebergabe-${u.id}`,
      node: <UebergabeHinweis sid={sid!} u={u} />,
    })
  zeilen.sort((x, y) => x.ts - y.ts)

  const ids = new Set(auftraege.map((a) => a.id))
  const zuege = (stand?.aktiv ?? []).filter((z) => ids.has(z.ticket) && z.run)
  const schluss = (
    <>
      {zuege.map((z) => (
        <LiveZug
          key={z.run}
          runId={z.run!}
          person={leute[z.agent] ?? { ...GRAU, name: z.name, color: z.color }}
        />
      ))}
      {auftraege
        .filter((a) => a.status === 'wartet_auf_kevin')
        .map((a) => (
          <Eskalation key={a.id} auftrag={a} leute={leute} />
        ))}
    </>
  )
  return { zeilen, schluss }
}
