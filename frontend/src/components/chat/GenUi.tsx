import { useContext, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAddEvent, useEvents } from '@/api/calendar'
import { formText, formWerte, splitUi, type ItemState, type UiSpec } from '@/lib/chat/genui'
import { useChat } from '@/stores/chat'
import { AntwortId } from './antwortId'
import { Chart } from './GenUiChart'
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

function Form({ spec }: { spec: Extract<UiSpec, { type: 'form' }> }) {
  const { t } = useTranslation()
  const send = useChat((st) => st.send)
  const naechste = useNaechsteEingabe()
  const [werte, setWerte] = useState<Record<string, string>>({})
  const [geschickt, setGeschickt] = useState(false)
  // Schon beantwortet (auch vor dem Neuladen): Werte aus der Nachricht zeigen.
  const erledigt = geschickt || naechste != null
  const zeige = geschickt || naechste == null ? werte : formWerte(spec, naechste)
  const setze = (name: string, v: string) => setWerte((w) => ({ ...w, [name]: v }))
  return (
    <form
      className={`${s.card} ${s.form}`}
      onSubmit={(e) => {
        e.preventDefault()
        const text = formText(spec, werte)
        if (!text || erledigt) return
        setGeschickt(true)
        void send(text, { hinten: true })
      }}
    >
      {spec.title && <div className={s.question}>{spec.title}</div>}
      <fieldset className={s.felder} disabled={erledigt}>
        {spec.fields.map((f) => {
          const props = {
            name: f.name,
            required: f.required,
            value: zeige[f.name] ?? '',
            className: s.eingabe,
            onChange: (
              e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
            ) => setze(f.name, e.target.value),
          }
          return (
            <label key={f.name} className={s.feld}>
              <span className={s.label}>
                {f.label}
                {f.required && <span className={s.pflicht}> *</span>}
              </span>
              {f.kind === 'textarea' ? (
                <textarea {...props} rows={3} placeholder={f.placeholder} />
              ) : f.kind === 'select' ? (
                <select {...props}>
                  <option value="">{t('— wählen —')}</option>
                  {f.options.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              ) : (
                <input {...props} type={f.kind} placeholder={f.placeholder} />
              )}
            </label>
          )
        })}
      </fieldset>
      <div className={s.formFuss}>
        {erledigt ? (
          <span className={s.done}>{t('✓ Abgeschickt')}</span>
        ) : (
          <button type="submit" className={s.add}>
            {spec.submit || t('Absenden')}
          </button>
        )}
      </div>
    </form>
  )
}

const ZEICHEN: Record<ItemState, string> = { done: '✓', failed: '✗', active: '●', open: '○' }
// Eigene Klassennamen: .done gibt es schon für „✓ Im Kalender“.
const PUNKT: Record<ItemState, string | undefined> = {
  done: s.punktDone,
  failed: s.punktFailed,
  active: s.punktActive,
  open: s.punktOpen,
}

function Checklist({ spec }: { spec: Extract<UiSpec, { type: 'checklist' }> }) {
  const { t } = useTranslation()
  const fertig = spec.items.filter((i) => i.state === 'done').length
  const fehler = spec.items.filter((i) => i.state === 'failed').length
  return (
    <div className={s.card}>
      <div className={s.listeKopf}>
        {spec.title && <span className={s.question}>{spec.title}</span>}
        <span className={s.zaehler}>
          {fertig}/{spec.items.length}
          {fehler > 0 && ` · ${t('{n} fehlgeschlagen', { n: fehler })}`}
        </span>
      </div>
      <div
        className={s.meter}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={spec.items.length}
        aria-valuenow={fertig}
      >
        <div className={s.meterFill} style={{ width: `${(fertig / spec.items.length) * 100}%` }} />
      </div>
      <ul className={s.liste}>
        {spec.items.map((it, i) => (
          <li key={i} className={PUNKT[it.state]}>
            <span className={s.zeichen} aria-hidden>
              {ZEICHEN[it.state]}
            </span>
            <span>
              {it.text}
              {it.state === 'failed' && <span className={s.srOnly}> ({t('fehlgeschlagen')})</span>}
              {it.state === 'active' && <span className={s.srOnly}> ({t('läuft')})</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Baustein({ spec }: { spec: UiSpec }) {
  switch (spec.type) {
    case 'choices':
      return <Choices spec={spec} />
    case 'event':
      return <EventCard spec={spec} />
    case 'form':
      return <Form spec={spec} />
    case 'chart':
      return <Chart spec={spec} />
    case 'checklist':
      return <Checklist spec={spec} />
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
