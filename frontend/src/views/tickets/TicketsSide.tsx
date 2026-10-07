import { useTranslation } from 'react-i18next'
import { useBoard } from '@/api/tickets'
import { useUi } from '@/stores/ui'
import { useTicketsAnsicht } from './store'
import s from './Tickets.module.css'

// Seitenleiste: neue Karte, darunter die Projekte, auf die sich das Board beschränken lässt.
export function TicketsSide() {
  const { t } = useTranslation()
  const { data } = useBoard()
  const { projekt, setProjekt, oeffne } = useTicketsAnsicht()
  const zu = useUi((st) => st.setSideOpen)
  const offen = (p: string | null) =>
    (data?.tickets ?? []).filter((x) => x.spalte !== 'done' && (!p || x.projekt === p)).length
  const wahl = (p: string | null) => (setProjekt(p), zu(false))

  return (
    <div>
      <button type="button" className={s.add} onClick={() => (oeffne('neu'), zu(false))}>
        ＋ {t('NEUES TICKET')}
      </button>
      <button
        type="button"
        className={`${s.projekt} ${!projekt ? s.sel : ''}`}
        onClick={() => wahl(null)}
      >
        <span className={s.name}>{t('Alle Projekte')}</span>
        <span className={s.zahl}>{offen(null)}</span>
      </button>
      {(data?.projekte ?? []).map((p) => (
        <button
          key={p.pfad}
          type="button"
          title={p.pfad}
          className={`${s.projekt} ${projekt === p.pfad ? s.sel : ''}`}
          onClick={() => wahl(projekt === p.pfad ? null : p.pfad)}
        >
          <span className={s.name}>▣ {p.name}</span>
          <span className={s.zahl}>{offen(p.pfad)}</span>
        </button>
      ))}
    </div>
  )
}
