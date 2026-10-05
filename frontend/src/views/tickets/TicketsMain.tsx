import { useTranslation } from 'react-i18next'
import { useTicketUebersicht } from '@/api/tickets'
import { useSettings } from '@/stores/settings'
import { tagName } from './format'
import { TicketKarte } from './TicketKarte'
import { useTicketsAnsicht } from './store'
import s from './Tickets.module.css'

// Hauptbereich: was an einem Tag je Projekt erledigt und was offen ist.
export function TicketsMain({ onDone }: { onDone?: () => void } = {}) {
  const { t } = useTranslation()
  const lang = useSettings((st) => st.boot.lang)
  const { data, isPending } = useTicketUebersicht()
  const { tag, cwd } = useTicketsAnsicht()
  const tage = data?.tage ?? []
  const tag_ = tag && tage.some((d) => d.tag === tag) ? tag : (tage[0]?.tag ?? null)
  const tagDaten = tage.find((d) => d.tag === tag_)
  const projekte = (tagDaten?.projekte ?? []).filter((p) => !cwd || p.cwd === cwd)

  return (
    <div className={s.wrap}>
      <h2 className={s.h2}>
        🎫{' '}
        {tag_ ? tagName(tag_, lang, (k) => t(k === 'heute' ? 'heute' : 'gestern')) : t('Tickets')}
      </h2>
      {!isPending && !tagDaten && (
        <div className={s.leer}>
          {t('Noch keine Tickets. Sie entstehen von selbst, sobald du in einer Session schreibst.')}
        </div>
      )}
      {projekte.map((p) => (
        <section key={p.cwd} className={s.projektblock}>
          <h3 className={s.h3} title={p.cwd}>
            ▣ {p.name}
            <span className={s.summe}>
              {p.erledigt > 0 && <span>✓ {p.erledigt}</span>}
              {p.offen > 0 && <span className={s.offen}>○ {p.offen}</span>}
            </span>
          </h3>
          {p.tickets.map((x) => (
            <TicketKarte key={`${x.session}:${x.nr}`} ticket={x} projekt={p} onDone={onDone} />
          ))}
        </section>
      ))}
    </div>
  )
}
