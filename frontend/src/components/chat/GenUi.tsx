import { useContext, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAddEvent, useEvents } from '@/api/calendar'
import { splitUi, type UiSpec } from '@/lib/chat/genui'
import { useChat } from '@/stores/chat'
import { AntwortId } from './antwortId'
import { Markdown } from './Markdown'
import s from './GenUi.module.css'

/** Was der Nutzer nach dieser Antwort als Nächstes geschrieben hat, sonst null.
 *  Gibt einen String zurück statt eines Objekts: zustand vergleicht mit ===. */
function useNaechsteEingabe(): string | null {
  const id = useContext(AntwortId)
  return useChat((st) => {
    const h = st.active()?.history ?? []
    const i = id ? h.findIndex((x) => x.id === id) : -1
    if (i < 0) return null
    const next = h.slice(i + 1).find((x) => x.kind === 'user')
    return next?.kind === 'user' ? next.text.trim() : null
  })
}

function Choices({ spec }: { spec: Extract<UiSpec, { type: 'choices' }> }) {
  const send = useChat((st) => st.send)
  const naechste = useNaechsteEingabe()
  const [geklickt, setGeklickt] = useState<string | null>(null)
  // Sobald unter der Frage eine Antwort steht, ist sie erledigt — auch nach
  // dem Neuladen, wenn vom Klick nichts mehr weiß.
  const gewaehlt =
    geklickt ?? (naechste != null && spec.options.includes(naechste) ? naechste : null)
  const erledigt = gewaehlt != null || naechste != null
  return (
    <div className={s.card}>
      {spec.question && <div className={s.question}>{spec.question}</div>}
      <div className={s.options}>
        {spec.options.map((o) => (
          <button
            key={o}
            type="button"
            className={`${s.option} ${gewaehlt === o ? s.chosen : ''}`}
            disabled={erledigt}
            onClick={() => {
              setGeklickt(o)
              // Läuft gerade noch etwas, hinten anstellen statt in den Zug zu funken.
              void send(o, { hinten: true })
            }}
          >
            {gewaehlt === o && '✓ '}
            {o}
          </button>
        ))}
      </div>
    </div>
  )
}

function EventCard({ spec }: { spec: Extract<UiSpec, { type: 'event' }> }) {
  const { t, i18n } = useTranslation()
  const events = useEvents()
  const add = useAddEvent()
  // Schon eingetragen (auch vom Assistenten selbst über cal.py)? Dann kein Knopf.
  const drin = (events.data ?? []).some(
    (e) => e.date === spec.date && e.time === spec.time && e.title === spec.title,
  )
  const tag = new Date(`${spec.date}T12:00:00`).toLocaleDateString(i18n.language, {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
  return (
    <div className={`${s.card} ${s.event}`}>
      <div className={s.icon}>📅</div>
      <div className={s.body}>
        <div className={s.title}>{spec.title}</div>
        <div className={s.when}>
          {tag}
          {spec.time ? ` · ${spec.time}` : ` · ${t('ganztägig')}`}
        </div>
        {spec.notes && <div className={s.notes}>{spec.notes}</div>}
        {add.isError && <div className={s.error}>⚠ {add.error.message}</div>}
      </div>
      {drin ? (
        <span className={s.done}>{t('✓ Im Kalender')}</span>
      ) : (
        <button
          type="button"
          className={s.add}
          disabled={add.isPending || events.isLoading}
          onClick={() =>
            add.mutate({
              date: spec.date,
              time: spec.time,
              title: spec.title,
              notes: spec.notes,
              prompt: '',
              repeat: '',
            })
          }
        >
          {add.isPending ? t('Trage ein …') : t('Eintragen')}
        </button>
      )}
    </div>
  )
}

function Baustein({ spec }: { spec: UiSpec }) {
  switch (spec.type) {
    case 'choices':
      return <Choices spec={spec} />
    case 'event':
      return <EventCard spec={spec} />
  }
}

/** Markdown einer Antwort, darin `ui`-Codeblöcke als Bausteine. */
export function RichMarkdown({
  text,
  streaming,
  className,
}: {
  text: string
  streaming?: boolean
  className?: string
}) {
  const { t } = useTranslation()
  const parts = splitUi(text, streaming)
  const [erst] = parts
  // Nur Text (auch ein unlesbarer Baustein, der jetzt Codeblock ist): wie bisher.
  if (parts.length <= 1 && erst?.t !== 'ui' && erst?.t !== 'pending')
    return <Markdown className={className} text={erst?.text ?? text} streaming={streaming} />
  return (
    <div className={className}>
      {parts.map((p, i) =>
        p.t === 'md' ? (
          <Markdown key={i} text={p.text} streaming={streaming && i === parts.length - 1} />
        ) : p.t === 'ui' ? (
          <Baustein key={i} spec={p.spec} />
        ) : (
          <div key={i} className={s.pending}>
            {t('baue Karte …')}
          </div>
        ),
      )}
    </div>
  )
}
