import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import {
  useSessionTickets,
  useTicketActions,
  type UebersichtProjekt,
  type UebersichtTicket,
} from '@/api/tickets'
import { useFirmaGeben, useTeamAn } from '@/api/team'
import { useAuftraegeAnsicht } from '../auftraege/store'
import { uhrzeit } from './format'
import { useOeffnen } from './oeffnen'
import s from './Tickets.module.css'

type T = UebersichtTicket

/** Die Nachrichten eines Ticket-Abschnitts: Sprung in den Verlauf, in ein anderes Ticket legen. */
function Nachrichten({
  ticket,
  projekt,
  oeffnen,
}: {
  ticket: T
  projekt: UebersichtProjekt
  oeffnen: ReturnType<typeof useOeffnen>
}) {
  const { t } = useTranslation()
  const alle = useSessionTickets(ticket.session).data
  const act = useTicketActions(ticket.session)
  const andere = (alle?.tickets ?? []).filter((x) => x.nr !== ticket.nr)
  return (
    <div className={s.msgs}>
      {ticket.nachrichten.map((m) => (
        <div key={m.id} className={s.msg}>
          <span className={s.zeit}>{uhrzeit(m.ts)}</span>
          <button
            type="button"
            className={s.text}
            title={t('Im Verlauf zeigen')}
            onClick={() => oeffnen(ticket, projekt.cwd, m.id)}
          >
            {m.text || t('(Bild)')}
          </button>
          {!!andere.length && (
            <select
              className={`${s.wahl} ${s.klein}`}
              value=""
              title={t('In ein anderes Ticket legen')}
              onChange={(e) => {
                if (e.target.value)
                  act.umhaengen.mutate({ uuids: [m.id], nr: Number(e.target.value) })
              }}
            >
              <option value="">↦</option>
              {andere.map((x) => (
                <option key={x.nr} value={x.nr}>
                  #{x.nr} {x.titel}
                </option>
              ))}
            </select>
          )}
        </div>
      ))}
      {ticket.gesamt > ticket.nachrichten.length && (
        <div className={s.rest}>
          {t('+ {n} Nachrichten an anderen Tagen', {
            n: ticket.gesamt - ticket.nachrichten.length,
          })}
        </div>
      )}
    </div>
  )
}

export function TicketKarte({
  ticket,
  projekt,
  onDone,
}: {
  ticket: T
  projekt: UebersichtProjekt
  /** Im Raum: die Karte schließen, wenn eine Session geöffnet wurde. */
  onDone?: () => void
}) {
  const { t } = useTranslation()
  const oeffnen = useOeffnen(onDone)
  const navigate = useNavigate()
  const teamAn = useTeamAn()
  const geben = useFirmaGeben()
  const oeffneAuftrag = useAuftraegeAnsicht((st) => st.oeffne)
  const act = useTicketActions(ticket.session)
  const [auf, setAuf] = useState(false)
  const [name, setName] = useState<string | null>(null)
  const alle = useSessionTickets(auf ? ticket.session : null).data
  const fertig = ticket.status === 'erledigt'
  const erste = ticket.nachrichten[0]?.ts ?? ticket.erstellt
  // Esc und Enter beenden das Feld selbst; das Blur, das beim Verschwinden des Feldes
  // folgt, darf dann nicht noch einmal speichern (oder bei Esc gar umbenennen).
  const fertigMit = useRef(false)
  const speichern = () => {
    if (fertigMit.current) return
    fertigMit.current = true
    const n = (name ?? '').trim()
    if (n && n !== ticket.titel) act.aendern.mutate({ nr: ticket.nr, titel: n })
    setName(null)
  }
  const abbrechen = () => {
    fertigMit.current = true
    setName(null)
  }
  const zurFirma = (id: string) => {
    oeffneAuftrag(id)
    navigate('/auftraege')
    onDone?.()
  }

  return (
    <div className={`${s.karte} ${fertig ? s.fertig : ''}`}>
      <div className={s.kopf}>
        <button
          type="button"
          className={s.haken}
          title={fertig ? t('Wieder öffnen') : t('Als erledigt markieren')}
          onClick={() =>
            act.aendern.mutate({ nr: ticket.nr, status: fertig ? 'offen' : 'erledigt' })
          }
        >
          {fertig ? '✓' : '○'}
        </button>
        {name === null ? (
          <button
            type="button"
            className={s.titel}
            title={ticket.session_titel || undefined}
            onClick={() => setAuf(!auf)}
          >
            <span className={s.nr}>#{ticket.nr}</span> {ticket.titel}
            {ticket.aktuell && <span className={s.aktuell}>▸ {t('aktuell')}</span>}
          </button>
        ) : (
          <input
            className={s.feld}
            autoFocus
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
            onBlur={speichern}
            onKeyDown={(e) => {
              if (e.key === 'Enter') speichern()
              else if (e.key === 'Escape') abbrechen()
            }}
          />
        )}
        <span className={s.meta}>
          {uhrzeit(erste)} · {ticket.gesamt} {t('Nachr.')}
        </span>
        {ticket.auftrag ? (
          <button
            type="button"
            className={s.mini}
            title={t('Bei der Firma — Auftrag ansehen')}
            onClick={() => zurFirma(ticket.auftrag!)}
          >
            🏢
          </button>
        ) : (
          teamAn &&
          !fertig && (
            <button
              type="button"
              className={s.mini}
              disabled={geben.isPending}
              title={t('An die Firma geben')}
              onClick={() =>
                geben.mutate(
                  { session: ticket.session, nr: ticket.nr },
                  { onSuccess: (j) => zurFirma(j.ticket.id), onError: (e) => alert(e.message) },
                )
              }
            >
              🏢→
            </button>
          )
        )}
        <button
          type="button"
          className={s.mini}
          title={t('Umbenennen')}
          onClick={() => {
            fertigMit.current = false
            setName(ticket.titel)
          }}
        >
          ✎
        </button>
        <button
          type="button"
          className={s.mini}
          title={t('Session im Chat öffnen')}
          onClick={() => oeffnen(ticket, projekt.cwd, ticket.nachrichten[0]?.id)}
        >
          ↗
        </button>
      </div>
      {auf && (
        <>
          <Nachrichten ticket={ticket} projekt={projekt} oeffnen={oeffnen} />
          <div className={s.aktionen}>
            {(alle?.tickets.length ?? 0) > 1 && (
              <select
                className={s.wahl}
                value=""
                onChange={(e) => {
                  const ziel = Number(e.target.value)
                  if (ziel && confirm(t('Mit #{n} zusammenführen?', { n: ziel })))
                    act.zusammenfuehren.mutate({ nr: ticket.nr, in: ziel })
                }}
              >
                <option value="">{t('⇢ Zusammenführen mit …')}</option>
                {alle!.tickets
                  .filter((x) => x.nr !== ticket.nr)
                  .map((x) => (
                    <option key={x.nr} value={x.nr}>
                      #{x.nr} {x.titel}
                    </option>
                  ))}
              </select>
            )}
            <button
              type="button"
              className={s.mini}
              title={t('Ticket löschen (die Nachrichten bleiben im Verlauf)')}
              onClick={() => {
                if (
                  confirm(
                    t('Ticket #{n} löschen? Die Nachrichten bleiben im Verlauf.', { n: ticket.nr }),
                  )
                )
                  act.loeschen.mutate(ticket.nr)
              }}
            >
              🗑
            </button>
          </div>
        </>
      )}
    </div>
  )
}
