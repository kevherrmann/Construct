import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSessionTickets, useTicketActions, useTicketsAn } from '@/api/tickets'
import { useSchliessen } from '@/hooks/useSchliessen'
import { useChat } from '@/stores/chat'
import { Eingabe, TicketZeile } from './TicketChip'
import m from './Message.module.css'
import s from './Tickets.module.css'

/** ✂ an einer eigenen Nachricht: ab hier ein neues Ticket, oder die Nachricht
 *  in ein anderes legen. Für nachträgliche Schnitte; der Chip und `/ticket`
 *  setzen sie vorher. */
export function TicketCut({ uuid }: { uuid: string }) {
  const { t } = useTranslation()
  const an = useTicketsAn()
  const sid = useChat((st) => st.active()?.sessionId ?? null)
  const q = useSessionTickets(sid)
  const act = useTicketActions(sid ?? '')
  const [open, setOpen] = useState(false)
  const zu = useCallback(() => setOpen(false), [])
  useSchliessen(open, zu)
  const d = q.data
  const heim = d?.tickets.find((x) => x.nachrichten.some((n) => n.id === uuid))
  if (!an || !sid || !d || !heim) return null
  const andere = [...d.tickets].reverse().filter((x) => x.nr !== heim.nr)

  return (
    <>
      <span className={m.schnitt} onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className={`${m.schere} ${open ? m.offen : ''}`}
          title={t('Ticket: ab hier neues Ticket oder in ein anderes verschieben')}
          onClick={() => setOpen(!open)}
        >
          ✂
        </button>
      </span>
      {open && (
        <div className={`${s.menu} ${s.unten}`} onClick={(e) => e.stopPropagation()}>
          <div className={s.kopf}>
            {t('GEHÖRT ZU')} #{heim.nr}
          </div>
          <Eingabe
            platz={t('✂ Ab hier neues Ticket (Titel) …')}
            knopf={t('Anlegen')}
            onEsc={zu}
            onOk={(titel) => {
              act.abHier.mutate({ uuid, titel })
              zu()
            }}
          />
          {!!andere.length && (
            <>
              <div className={s.kopf}>{t('IN EIN ANDERES VERSCHIEBEN')}</div>
              <div className={s.liste}>
                {andere.map((x) => (
                  <TicketZeile
                    key={x.nr}
                    t={x}
                    aktuell={null}
                    onClick={() => {
                      act.umhaengen.mutate({ uuids: [uuid], nr: x.nr })
                      zu()
                    }}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </>
  )
}

/** Linie im Verlauf: hier beginnt (oder setzt sich fort) ein Ticket. */
export function TicketTrenner({
  nr,
  titel,
  erledigt,
}: {
  nr: number
  titel: string
  erledigt: boolean
}) {
  return (
    <div className={s.trenner} data-ticket={nr}>
      <span className={erledigt ? s.fertig : ''}>
        <b>#{nr}</b> {titel}
      </span>
      {erledigt && <span>✓</span>}
    </div>
  )
}
