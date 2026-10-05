import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useFirmaGeben, useTeamAn } from '@/api/team'
import { useAuftraegeAnsicht } from '@/views/auftraege/store'
import { useSessionTickets, useTicketActions, useTicketsAn, type Ticket } from '@/api/tickets'
import { useSchliessen } from '@/hooks/useSchliessen'
import { useChat } from '@/stores/chat'
import s from './Tickets.module.css'

const zeichen = (t: Ticket, aktuell: number | null) =>
  t.nr === aktuell ? '▸' : t.status === 'erledigt' ? '✓' : '○'

/** Zeile eines Tickets in einer Auswahl. */
export function TicketZeile({
  t,
  aktuell,
  onClick,
}: {
  t: Ticket
  aktuell: number | null
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className={`${s.item} ${t.nr === aktuell ? s.sel : ''} ${t.status === 'erledigt' ? s.fertig : ''}`}
      onClick={onClick}
    >
      <span className={s.zeichen}>{zeichen(t, aktuell)}</span>
      <span className={s.nr}>#{t.nr}</span>
      <span className={s.titel} title={t.titel}>
        {t.titel}
      </span>
      {t.auftrag && <span title="Firma">🏢</span>}
    </button>
  )
}

/** Eingabezeile mit Enter = ok, Esc = zu. */
export function Eingabe({
  platz,
  start = '',
  knopf,
  onOk,
  onEsc,
}: {
  platz: string
  start?: string
  knopf: string
  onOk: (text: string) => void
  onEsc?: () => void
}) {
  const [v, setV] = useState(start)
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => ref.current?.focus(), [])
  const ok = () => v.trim() && onOk(v.trim())
  return (
    <div className={s.zeile}>
      <input
        ref={ref}
        className={s.feld}
        value={v}
        placeholder={platz}
        maxLength={80}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            ok()
          } else if (e.key === 'Escape') onEsc?.()
        }}
      />
      <button type="button" className={s.knopf} onClick={ok}>
        {knopf}
      </button>
    </div>
  )
}

/** Das Ticket, in das die nächste Nachricht geht — und die Wahl eines anderen.
 *  Alles hier kostet keine Tokens. */
export function TicketChip() {
  const { t } = useTranslation()
  const an = useTicketsAn()
  const conv = useChat((st) => st.active())
  const setVorgabe = useChat((st) => st.setTicketVorgabe)
  const sid = conv?.sessionId ?? null
  const q = useSessionTickets(sid)
  const [open, setOpen] = useState(false)
  const [umbenennen, setUmbenennen] = useState(false)
  const act = useTicketActions(sid ?? '')
  const teamAn = useTeamAn()
  const geben = useFirmaGeben()
  const navigate = useNavigate()
  const oeffneAuftrag = useAuftraegeAnsicht((st) => st.oeffne)
  useSchliessen(open, () => {
    setOpen(false)
    setUmbenennen(false)
  })
  if (!an || !conv || conv.agent) return null

  const d = q.data
  const ak = d?.tickets.find((x) => x.nr === d.aktuell)
  const vorgabe = conv.ticketVorgabe
  const label = vorgabe ? (
    <>
      ＋ <span className={s.name}>{vorgabe}</span>
    </>
  ) : ak ? (
    <>
      {ak.status === 'erledigt' ? '✓' : '▸'} <span className={s.nr}>#{ak.nr}</span>{' '}
      <span className={s.name}>{ak.titel}</span>
    </>
  ) : (
    <span className={s.leer}>🎫 {t('Ticket')}</span>
  )
  const zu = () => {
    setOpen(false)
    setUmbenennen(false)
  }
  const neu = (titel: string) => {
    if (sid) act.schnitt.mutate({ titel, cwd: conv.cwd ?? '' })
    else setVorgabe(titel)
    zu()
  }
  const liste = [...(d?.tickets ?? [])].reverse()

  return (
    <div className={s.chip} onClick={(e) => e.stopPropagation()}>
      {open && (
        <div className={s.menu}>
          {!!liste.length && (
            <>
              <div className={s.kopf}>{t('NÄCHSTE NACHRICHT GEHÖRT ZU')}</div>
              <div className={s.liste}>
                {liste.map((x) => (
                  <TicketZeile
                    key={x.nr}
                    t={x}
                    aktuell={d?.aktuell ?? null}
                    onClick={() => {
                      act.waehlen.mutate(x.nr)
                      zu()
                    }}
                  />
                ))}
              </div>
            </>
          )}
          {ak && !umbenennen && (
            <div className={s.zeile}>
              <button
                type="button"
                className={s.knopf}
                onClick={() => {
                  act.aendern.mutate({
                    nr: ak.nr,
                    status: ak.status === 'erledigt' ? 'offen' : 'erledigt',
                  })
                  zu()
                }}
              >
                {ak.status === 'erledigt' ? t('↺ Wieder öffnen') : t('✓ Erledigt')}
              </button>
              <button type="button" className={s.knopf} onClick={() => setUmbenennen(true)}>
                {t('✎ Umbenennen')}
              </button>
              {teamAn && !ak.auftrag && ak.status !== 'erledigt' && sid && (
                <button
                  type="button"
                  className={s.knopf}
                  disabled={geben.isPending}
                  title={t('Die Nachrichten dieses Tickets gehen als Auftrag an die Firma')}
                  onClick={() =>
                    geben.mutate(
                      { session: sid, nr: ak.nr },
                      {
                        onSuccess: (j) => {
                          oeffneAuftrag(j.ticket.id)
                          navigate('/auftraege')
                          zu()
                        },
                        onError: (e) => alert(e.message),
                      },
                    )
                  }
                >
                  🏢 {t('An die Firma')}
                </button>
              )}
            </div>
          )}
          {ak && umbenennen && (
            <Eingabe
              platz={t('Neuer Name')}
              start={ak.titel}
              knopf={t('OK')}
              onEsc={() => setUmbenennen(false)}
              onOk={(titel) => {
                act.aendern.mutate({ nr: ak.nr, titel })
                zu()
              }}
            />
          )}
          <Eingabe
            platz={t('＋ Neues Ticket (Titel) …')}
            knopf={t('Anlegen')}
            onOk={neu}
            onEsc={zu}
          />
        </div>
      )}
      <button
        type="button"
        className={`${s.bar} ${open ? s.offen : ''}`}
        title={t('Ticket: zu welcher Aufgabe gehört die nächste Nachricht?')}
        onClick={() => setOpen(!open)}
      >
        {label} <span>▾</span>
      </button>
    </div>
  )
}
