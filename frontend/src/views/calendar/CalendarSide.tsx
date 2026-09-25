import { useTranslation } from 'react-i18next'
import { useEvents } from '@/api/calendar'
import { locale } from '@/lib/i18n'
import { useSettings } from '@/stores/settings'
import { parseYMD, todayYMD, upcoming } from './dates'
import { useCalendar } from './store'
import s from './CalendarSide.module.css'

// Seitenleiste: "Anstehend" — jeder Termin mit seinem nächsten Vorkommen.
export function CalendarSide() {
  const { t } = useTranslation()
  const lang = useSettings((st) => st.boot.lang)
  const { data, isPending } = useEvents()
  const openAdd = useCalendar((st) => st.openAdd)
  const jump = useCalendar((st) => st.jump)
  const tStr = todayYMD()
  const up = upcoming(data ?? [], tStr)

  return (
    <div>
      <button className={s.add} onClick={openAdd}>
        {t('＋ TERMIN')}
      </button>
      <div className={s.uh}>{t('ANSTEHEND')}</div>
      {!isPending && !up.length && <div className={s.hint}>{t('Keine anstehenden Termine.')}</div>}
      {up.map(({ e, d }) => (
        <div
          key={e.id}
          className={`${s.up} ${d === tStr ? s.isToday : ''}`}
          onClick={() => jump(d)}
        >
          <span className={s.t}>
            {e.repeat === 'yearly' ? '🔁 ' : ''}
            {e.prompt ? '🤖 ' : ''}
            {e.time ? `${e.time} · ` : ''}
            {e.title}
          </span>
          <span className={s.d}>
            {d === tStr
              ? t('heute')
              : parseYMD(d).toLocaleDateString(locale(lang), {
                  weekday: 'short',
                  day: '2-digit',
                  month: '2-digit',
                })}
          </span>
        </div>
      ))}
    </div>
  )
}
