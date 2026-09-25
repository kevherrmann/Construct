import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useAddEvent, useDeleteEvent, type ActivityProject, type CalEvent } from '@/api/calendar'
import { locale } from '@/lib/i18n'
import { useSettings } from '@/stores/settings'
import { baseName, parseYMD } from './dates'
import { useCalendar } from './store'
import s from './DayPanel.module.css'

interface Props {
  ds: string
  events: CalEvent[]
  /** Tagebuch dieses Tages: woran gearbeitet wurde. */
  act: ActivityProject[]
}

// Tages-Detail unter dem Grid: Termine, Tagebuch und Eintragen.
export function DayPanel({ ds, events, act }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const lang = useSettings((st) => st.boot.lang)
  const assistant = useSettings((st) => st.boot.assistant)
  const focusAdd = useCalendar((st) => st.focusAdd)
  const focusDone = useCalendar((st) => st.focusDone)
  const add = useAddEvent()
  const del = useDeleteEvent()
  const [time, setTime] = useState('')
  const [title, setTitle] = useState('')
  const [prompt, setPrompt] = useState('')
  const [yearly, setYearly] = useState(false)
  const timeRef = useRef<HTMLInputElement>(null)
  const titleRef = useRef<HTMLInputElement>(null)

  // "＋ TERMIN" in der Seitenleiste: gleich lostippen können.
  useEffect(() => {
    if (!focusAdd) return
    titleRef.current?.focus()
    focusDone()
  }, [focusAdd, focusDone])

  const head = parseYMD(ds).toLocaleDateString(locale(lang), {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })

  const submit = () => {
    const ti = title.trim()
    const tm = time.trim()
    const pr = prompt.trim()
    if (!ti) return titleRef.current?.focus()
    if (pr && !tm) return timeRef.current?.focus() // Aufgabe braucht Uhrzeit
    add.mutate(
      { date: ds, time: tm, title: ti, prompt: pr, repeat: yearly ? 'yearly' : '' },
      {
        onSuccess: () => {
          setTime('')
          setTitle('')
          setPrompt('')
          setYearly(false)
        },
      },
    )
  }

  return (
    <div className={s.day}>
      <h3>📅 {head}</h3>
      {events.length ? (
        events.map((e) => (
          <div key={e.id} className={s.ev}>
            <span className={s.et}>{e.time || (e.repeat === 'yearly' ? '🔁' : '⬤')}</span>
            <span className={s.etitle}>
              {e.prompt ? '🤖 ' : ''}
              {e.title}
              {e.notes && <span className={s.enote}> — {e.notes}</span>}
              {e.prompt && (
                <span
                  className={s.enote}
                  title={t('läuft zur Termin-Zeit automatisch, Ergebnis per Telegram')}
                >
                  {' '}
                  {t('— Aufgabe:')} {e.prompt.slice(0, 120)}
                </span>
              )}
            </span>
            <span className={s.edel} title={t('löschen')} onClick={() => del.mutate(e.id)}>
              ✕
            </span>
          </div>
        ))
      ) : (
        <div className={s.none}>{t('Keine Termine an diesem Tag.')}</div>
      )}
      {act.length > 0 && (
        <>
          <div className={s.acth}>{t('🗂 WORAN GEARBEITET')}</div>
          {act.map((p) => (
            <div key={p.cwd} className={s.proj}>
              <div className={s.cph} title={p.cwd}>
                📂 {baseName(p.cwd)}
                <span className={s.cpn}>
                  {p.n === 1 ? t('1 Eingabe') : t('{n} Eingaben', { n: p.n })}
                </span>
              </div>
              {p.sessions.map((se) => (
                <div
                  key={se.id}
                  className={s.cps}
                  title={t('Session öffnen')}
                  // Der Chat ist noch nicht umgezogen: er soll die Session aus
                  // den Parametern öffnen (project braucht /api/sessions/…).
                  onClick={() =>
                    navigate(
                      `/chat?session=${encodeURIComponent(se.id)}&project=${encodeURIComponent(se.project)}`,
                    )
                  }
                >
                  ↳ {se.title}
                </div>
              ))}
            </div>
          ))}
        </>
      )}
      <div className={s.add}>
        <input
          ref={timeRef}
          className={s.ciTime}
          placeholder={t('HH:MM')}
          maxLength={5}
          inputMode="numeric"
          value={time}
          onChange={(e) => setTime(e.target.value)}
        />
        <input
          ref={titleRef}
          className={s.ciTitle}
          placeholder={t('Termin eintragen (z.B. Zahnarzt)')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              submit()
            }
          }}
        />
        <label className={s.ciRep} title={t('jedes Jahr wiederholen (z.B. Geburtstag)')}>
          <input type="checkbox" checked={yearly} onChange={(e) => setYearly(e.target.checked)} />{' '}
          {t('🔁 jährlich')}
        </label>
        <button onClick={submit}>{t('＋ Eintragen')}</button>
      </div>
      <div className={s.add}>
        <input
          className={s.ciTitle}
          placeholder={t(
            '🤖 {a}-Aufgabe zur Termin-Zeit (optional) — Ergebnis kommt per Telegram',
            { a: assistant },
          )}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
      </div>
    </div>
  )
}
