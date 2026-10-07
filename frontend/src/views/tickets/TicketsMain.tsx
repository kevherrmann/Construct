import { useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  projektName,
  SPALTEN,
  SPALTEN_NAME,
  useBoard,
  useTicketActions,
  type Spalte,
  type Ticket,
} from '@/api/tickets'
import { useTicketsAnsicht } from './store'
import { TicketDialog } from './TicketDialog'
import s from './Tickets.module.css'

// So viele Karten zeigt Done, bevor "ältere" aufklappt: dort sammelt sich alles.
const DONE_SICHTBAR = 15

function Karte({
  t: k,
  mitProjekt,
  onOeffnen,
}: {
  t: Ticket
  mitProjekt: boolean
  onOeffnen: () => void
}) {
  const { t } = useTranslation()
  const [zieht, setZieht] = useState(false)
  const gepusht = k.commits.length > 0 && k.commits.every((c) => c.gepusht)
  return (
    <button
      type="button"
      draggable
      className={`${s.karte} ${zieht ? s.zieht : ''}`}
      onClick={onOeffnen}
      onDragStart={(e) => {
        e.dataTransfer.setData('text/x-ticket', String(k.nr))
        e.dataTransfer.effectAllowed = 'move'
        setZieht(true)
      }}
      onDragEnd={() => setZieht(false)}
    >
      <span className={s.kzeile}>
        <span className={s.nr}>T-{k.nr}</span>
        {mitProjekt && k.projekt && <span className={s.pname}>▣ {projektName(k.projekt)}</span>}
      </span>
      <span className={s.ktitel}>{k.titel}</span>
      {(k.commits.length > 0 || k.auftrag) && (
        <span className={s.kfuss}>
          {k.auftrag && <span title={t('Die Firma arbeitet daran')}>🏢</span>}
          {k.commits.length > 0 && (
            <span title={t('Commits')}>
              ⎇ {k.commits.length}
              {gepusht ? ' ✓' : ''}
            </span>
          )}
        </span>
      )}
    </button>
  )
}

function SpalteView({
  spalte,
  karten,
  mitProjekt,
}: {
  spalte: Spalte
  karten: Ticket[]
  mitProjekt: boolean
}) {
  const { t } = useTranslation()
  const oeffne = useTicketsAnsicht((st) => st.oeffne)
  const act = useTicketActions()
  const [ueber, setUeber] = useState(false)
  const [alle, setAlle] = useState(false)
  const sichtbar = spalte === 'done' && !alle ? karten.slice(0, DONE_SICHTBAR) : karten
  const nimmt = (e: DragEvent) => e.dataTransfer.types.includes('text/x-ticket')
  return (
    <section
      className={`${s.spalte} ${ueber ? s.ueber : ''}`}
      onDragOver={(e) => {
        if (!nimmt(e)) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        setUeber(true)
      }}
      onDragLeave={(e) => {
        // Nur wenn der Zeiger die Spalte verlässt, nicht beim Wechsel auf eine Karte darin.
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setUeber(false)
      }}
      onDrop={(e) => {
        setUeber(false)
        const nr = Number(e.dataTransfer.getData('text/x-ticket'))
        if (!nr) return
        e.preventDefault()
        const k = karten.find((x) => x.nr === nr)
        if (!k) act.aendern.mutate({ nr, spalte })
      }}
    >
      <header className={s.skopf}>
        {t(SPALTEN_NAME[spalte]).toUpperCase()}
        <span className={s.zahl}>{karten.length}</span>
        {spalte === 'neu' && (
          <button
            type="button"
            className={s.splus}
            title={t('Neues Ticket')}
            onClick={() => oeffne('neu')}
          >
            ＋
          </button>
        )}
      </header>
      <div className={s.karten}>
        {sichtbar.map((k) => (
          <Karte key={k.nr} t={k} mitProjekt={mitProjekt} onOeffnen={() => oeffne(k.nr)} />
        ))}
        {!karten.length && <div className={s.leer}>—</div>}
        {karten.length > sichtbar.length && (
          <button type="button" className={s.mehr} onClick={() => setAlle(true)}>
            {t('+ {n} ältere', { n: karten.length - sichtbar.length })}
          </button>
        )}
      </div>
    </section>
  )
}

// Hauptbereich: das Board. Karten wandern von selbst (Commits, Firma, Push) und
// lassen sich von Hand ziehen.
export function TicketsMain({ onDone }: { onDone?: () => void } = {}) {
  const { t } = useTranslation()
  const { data, isPending } = useBoard()
  const projekt = useTicketsAnsicht((st) => st.projekt)
  const tickets = (data?.tickets ?? []).filter((x) => !projekt || x.projekt === projekt)
  // Zuletzt bewegt oben: das ist, woran gerade gearbeitet wird.
  const sortiert = [...tickets].sort((a, b) => b.geaendert.localeCompare(a.geaendert))

  return (
    <div className={s.wrap}>
      <h2 className={s.h2}>🎫 {projekt ? projektName(projekt) : t('Tickets')}</h2>
      {!isPending && !data?.tickets.length && (
        <div className={s.leer}>
          {t(
            'Noch keine Tickets. Jeder Commit des Assistenten wird zu einer Karte, eigene legst du mit ＋ an.',
          )}
        </div>
      )}
      <div className={s.board}>
        {SPALTEN.map((sp) => (
          <SpalteView
            key={sp}
            spalte={sp}
            karten={sortiert.filter((x) => x.spalte === sp)}
            mitProjekt={!projekt}
          />
        ))}
      </div>
      <TicketDialog onDone={onDone} />
    </div>
  )
}
