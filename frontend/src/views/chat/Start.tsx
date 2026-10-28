import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useEvents } from '@/api/calendar'
import { useSessions, type SessionInfo } from '@/api/chat'
import { useSessionOeffnen } from '@/hooks/useSessionOeffnen'
import { datumsFormat } from '@/lib/format'
import { useChat } from '@/stores/chat'
import { useSettings } from '@/stores/settings'
import { todayYMD, upcoming } from '@/views/calendar/dates'
import s from './Start.module.css'

/** Uhrzeit, die zur vollen Minute weiterspringt — mehr braucht die Begrüßung nicht. */
function useMinute() {
  const [jetzt, setJetzt] = useState(() => new Date())
  useEffect(() => {
    let id: ReturnType<typeof setTimeout>
    const weiter = () => {
      id = setTimeout(
        () => {
          setJetzt(new Date())
          weiter()
        },
        60_000 - (Date.now() % 60_000) + 50,
      )
    }
    weiter()
    return () => clearTimeout(id)
  }, [])
  return jetzt
}

function gruss(h: number, mitName: boolean) {
  if (h < 5) return mitName ? 'Noch wach, {name}?' : 'Noch wach?'
  if (h < 11) return mitName ? 'Guten Morgen, {name}' : 'Guten Morgen'
  if (h < 17) return mitName ? 'Hallo, {name}' : 'Hallo'
  if (h < 22) return mitName ? 'Guten Abend, {name}' : 'Guten Abend'
  return mitName ? 'Späte Schicht, {name}?' : 'Späte Schicht?'
}

// Ohne eingetragenen Namen liefert der Server einen Platzhalter — „Hallo, der
// Nutzer“ wäre schlimmer als gar kein Name.
const PLATZHALTER = new Set(['der Nutzer', 'the user'])

const tage = (von: string, bis: string) =>
  Math.round((Date.parse(`${bis}T12:00:00`) - Date.parse(`${von}T12:00:00`)) / 86_400_000)

/** Statt einer leeren Fläche: Begrüßung, was ansteht, und ein paar Einstiege. */
export function Start() {
  const { t, i18n } = useTranslation()
  const jetzt = useMinute()
  const roh = useSettings((st) => st.settings.names.user || st.boot.user)
  const name = PLATZHALTER.has(roh) ? '' : roh
  const kalender = useSettings((st) => st.settings.tiles.kalender)
  const events = useEvents()
  const sessions = useSessions()
  const send = useChat((st) => st.send)
  const oeffnen = useSessionOeffnen()

  const heute = todayYMD()
  const anstehend = kalender ? upcoming(events.data ?? [], heute, 3) : []
  const letzte = (sessions.data?.sessions ?? [])
    .filter((x) => !x.archived && !x.agent && x.title)
    .reduce<SessionInfo | null>((best, x) => (!best || x.mtime > best.mtime ? x : best), null)

  const wann = (d: string) => {
    const n = tage(heute, d)
    if (n === 0) return t('heute')
    if (n === 1) return t('morgen')
    return datumsFormat(i18n.language, {
      weekday: 'short',
      day: '2-digit',
      month: '2-digit',
    }).format(new Date(`${d}T12:00:00`))
  }
  const kurz = (x: string, n = 42) => (x.length > n ? `${x.slice(0, n - 1)}…` : x)

  return (
    <div className={s.start}>
      <h1 className={s.gruss}>{t(gruss(jetzt.getHours(), !!name), { name })}</h1>
      <div className={s.datum}>
        {datumsFormat(i18n.language, { weekday: 'long', day: 'numeric', month: 'long' }).format(
          jetzt,
        )}
        {' · '}
        {datumsFormat(i18n.language, { hour: '2-digit', minute: '2-digit' }).format(jetzt)}
      </div>

      {anstehend.length > 0 && (
        <section className={s.karte}>
          <div className={s.kopf}>{t('Als Nächstes')}</div>
          <ul className={s.termine}>
            {anstehend.map(({ e, d }) => (
              <li key={`${e.id}-${d}`}>
                <span className={s.wann}>
                  {wann(d)}
                  {e.time ? ` · ${e.time}` : ''}
                </span>
                <span className={s.titel}>{e.title}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className={s.chips}>
        {kalender && (
          <button type="button" onClick={() => void send(t('Was steht diese Woche an?'))}>
            📅 {t('Was steht diese Woche an?')}
          </button>
        )}
        {letzte && (
          <button type="button" onClick={() => oeffnen(letzte.id, letzte.cwd)} title={letzte.title}>
            ↻ {t('Weiter mit „{titel}“', { titel: kurz(letzte.title) })}
          </button>
        )}
        <button type="button" onClick={() => void send(t('Was kannst du alles für mich tun?'))}>
          ✨ {t('Was kannst du alles?')}
        </button>
      </div>

      <div className={s.hinweis}>{t('Ordner unten wählbar, dann schreib los.')}</div>
    </div>
  )
}
