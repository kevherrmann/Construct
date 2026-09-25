import { useTranslation } from 'react-i18next'
import { useActivity, useEvents } from '@/api/calendar'
import { useSettings } from '@/stores/settings'
import { baseName, eventsOn, gridRange, monthGrid, monthName, todayYMD, weekdays } from './dates'
import { DayPanel } from './DayPanel'
import { useCalendar } from './store'
import s from './CalendarMain.module.css'

// Großer Monats-Grid im Hauptbereich. Termine leben in events.json (Backend):
// der Assistent schreibt per cal.py hinein, die Oberfläche per /api/events.
export function CalendarMain() {
  const { t } = useTranslation()
  const lang = useSettings((st) => st.boot.lang)
  const { year, month, sel, prev, next, today, select } = useCalendar()
  const events = useEvents().data ?? []
  // Das Grid steht sofort, die Tagebuch-Chips kommen einen Wimpernschlag später dazu.
  const [start, end] = gridRange(year, month)
  const act = useActivity(start, end).data ?? {}
  const tStr = todayYMD()

  return (
    <div className={s.page}>
      <div className={s.wrap}>
        <div className={s.top}>
          <button className={s.nav} title={t('Vorheriger Monat')} onClick={prev}>
            ‹
          </button>
          <h2>
            {monthName(lang, month)} {year}
          </h2>
          <button className={s.tbtn} onClick={today}>
            {t('HEUTE')}
          </button>
          <button className={s.nav} title={t('Nächster Monat')} onClick={next}>
            ›
          </button>
        </div>
        <div className={s.dow}>
          {weekdays(lang).map((d, i) => (
            <span key={d} className={i >= 5 ? s.we : undefined}>
              {d}
            </span>
          ))}
        </div>
        <div className={s.grid}>
          {monthGrid(year, month).map(({ ds, day, other }) => {
            const evs = eventsOn(events, ds)
            const projs = act[ds] ?? []
            const cls = [s.cell, other && s.other, ds === tStr && s.today, ds === sel && s.sel]
            return (
              <div key={ds} className={cls.filter(Boolean).join(' ')} onClick={() => select(ds)}>
                <span className={s.dnum}>{day}</span>
                {evs.slice(0, 3).map((e) => (
                  <div key={e.id} className={`${s.chip} ${e.time ? '' : s.allday}`}>
                    {e.prompt ? '🤖 ' : ''}
                    {e.time ? `${e.time} ` : ''}
                    {e.title}
                  </div>
                ))}
                {evs.length > 3 && (
                  <div className={s.more}>{t('+{n} mehr', { n: evs.length - 3 })}</div>
                )}
                {projs.length > 0 && (
                  <div className={s.act} title={projs.map((p) => baseName(p.cwd)).join(', ')}>
                    🗂 {baseName(projs[0]!.cwd)}
                    {projs.length > 1 ? ` +${projs.length - 1}` : ''}
                  </div>
                )}
              </div>
            )
          })}
        </div>
        {sel && <DayPanel key={sel} ds={sel} events={eventsOn(events, sel)} act={act[sel] ?? []} />}
      </div>
    </div>
  )
}
