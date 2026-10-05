import { useTranslation } from 'react-i18next'
import { useTicketUebersicht, useTicketsAn } from '@/api/tickets'
import { dateYMD } from '@/views/calendar/dates'
import { useChat } from '@/stores/chat'
import { parallelMatrix } from './kamera'
import { WAND_TAFEL } from './stationen'
import s from './Raum.module.css'

// Die Tafel wird in diesem festen Maß gezeichnet und als Ganzes vor die Wand
// gelegt — Schrift und Linien skalieren mit dem Raum.
const TW = 800
const TH = 500
/** Mehr passt nicht lesbar auf die Fläche; der Rest wird gezählt. */
const ZEILEN = 5

/** Ein Hologramm an der Rückwand: was heute im Projekt der Session erledigt
 *  und was offen ist. Dieselben Daten wie die Kachel Tickets. */
export function Tafel({
  welt,
  weich = false,
}: {
  welt: { w: number; h: number }
  weich?: boolean
}) {
  const { t } = useTranslation()
  const an = useTicketsAn()
  const cwd = useChat((st) => st.active()?.cwd ?? st.folder)
  const { data } = useTicketUebersicht()
  if (!welt.w || !an) return null
  const k = welt.w / 2048
  const [ol, or, ul] = WAND_TAFEL.map(([x, y]) => [x * k, y * k] as const)

  const heute = data?.tage.find((d) => d.tag === dateYMD(new Date()))
  // Das Projekt der geöffneten Session; hat es heute nichts, das zuletzt bearbeitete.
  const projekt = heute?.projekte.find((p) => p.cwd === cwd) ?? heute?.projekte[0]
  const offen = projekt?.offen ?? 0
  const fertig = projekt?.erledigt ?? 0
  // Offene zuerst, dann die zuletzt erledigten.
  const zeilen = [...(projekt?.tickets ?? [])]
    .sort((a, b) => Number(a.status === 'erledigt') - Number(b.status === 'erledigt'))
    .slice(0, ZEILEN)
  const rest = (projekt?.tickets.length ?? 0) - zeilen.length

  return (
    <div
      className={`${s.tafel} ${weich ? s.tafelWeich : ''}`}
      style={{ width: TW, height: TH, transform: parallelMatrix(TW, TH, ol!, or!, ul!) }}
      aria-hidden
    >
      <i className={`${s.ecke} ${s.eckeOL}`} />
      <i className={`${s.ecke} ${s.eckeOR}`} />
      <i className={`${s.ecke} ${s.eckeUL}`} />
      <i className={`${s.ecke} ${s.eckeUR}`} />
      <i className={s.tafelStrahl} />
      <div className={s.tafelKopf}>
        <span>{t('TICKETS')}</span>
        <span className={s.tafelProjekt}>{projekt?.name ?? ''}</span>
      </div>
      <div className={s.tafelZahlen}>
        <span>
          <b>{fertig}</b>
          <em>{t('erledigt')}</em>
        </span>
        <span className={s.tafelOffen}>
          <b>{offen}</b>
          <em>{t('offen')}</em>
        </span>
      </div>
      <ul className={s.tafelListe}>
        {zeilen.map((x) => (
          <li key={`${x.session}:${x.nr}`} className={x.status === 'erledigt' ? s.tafelFertig : ''}>
            <span>{x.status === 'erledigt' ? '✓' : x.aktuell ? '▸' : '○'}</span>
            <span className={s.tafelTitel}>{x.titel}</span>
          </li>
        ))}
        {!zeilen.length && <li className={s.tafelLeer}>{t('Heute noch keine Tickets')}</li>}
        {rest > 0 && <li className={s.tafelLeer}>{t('+ {n} weitere', { n: rest })}</li>}
      </ul>
    </div>
  )
}
