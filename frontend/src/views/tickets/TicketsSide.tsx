import { useTranslation } from 'react-i18next'
import { useTicketUebersicht } from '@/api/tickets'
import { useSettings } from '@/stores/settings'
import { useUi } from '@/stores/ui'
import { tagName } from './format'
import { useTicketsAnsicht } from './store'
import s from './Tickets.module.css'

// Seitenleiste: die Tage, an denen es Tickets gab, darunter die Projekte des gewählten Tages.
export function TicketsSide() {
  const { t } = useTranslation()
  const lang = useSettings((st) => st.boot.lang)
  const { data, isPending } = useTicketUebersicht()
  const { tag, cwd, wahl: waehle } = useTicketsAnsicht()
  const zu = useUi((st) => st.setSideOpen)
  const wahl = (t: string | null, c: string | null = null) => (waehle(t, c), zu(false))
  const tage = data?.tage ?? []
  const aktiv = tag && tage.some((d) => d.tag === tag) ? tag : (tage[0]?.tag ?? null)

  return (
    <div>
      {!isPending && !tage.length && (
        <div className={s.hint}>
          {t('Noch keine Tickets. Sie entstehen von selbst, sobald du in einer Session schreibst.')}
        </div>
      )}
      {tage.map((d) => {
        const offen = d.projekte.reduce((n, p) => n + p.offen, 0)
        const fertig = d.projekte.reduce((n, p) => n + p.erledigt, 0)
        const sel = d.tag === aktiv
        return (
          <div key={d.tag}>
            <button
              type="button"
              className={`${s.tag} ${sel && !cwd ? s.sel : ''}`}
              onClick={() => wahl(d.tag)}
            >
              <span>{tagName(d.tag, lang, (k) => t(k === 'heute' ? 'heute' : 'gestern'))}</span>
              <span className={s.zahl}>
                {fertig > 0 && <span>✓ {fertig}</span>}
                {offen > 0 && <span className={s.offen}>○ {offen}</span>}
              </span>
            </button>
            {sel &&
              d.projekte.length > 1 &&
              d.projekte.map((p) => (
                <button
                  key={p.cwd}
                  type="button"
                  className={`${s.projekt} ${cwd === p.cwd ? s.sel : ''}`}
                  onClick={() => wahl(d.tag, cwd === p.cwd ? null : p.cwd)}
                >
                  <span className={s.name}>▣ {p.name}</span>
                  <span className={s.zahl}>
                    {p.erledigt > 0 && <span>✓ {p.erledigt}</span>}
                    {p.offen > 0 && <span className={s.offen}>○ {p.offen}</span>}
                  </span>
                </button>
              ))}
          </div>
        )
      })}
    </div>
  )
}
