import { useEffect, useRef, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { SECTIONS, sectionDomId, type SectionId } from './sections'
import s from './Settings.module.css'

/** Ein Kasten der Einstellungsseite mit Überschrift aus SECTIONS. */
export function Section({ id, children }: { id: SectionId; children: ReactNode }) {
  const { t } = useTranslation()
  const title = SECTIONS.find((x) => x.id === id)!.title
  return (
    <div className={s.sec} id={sectionDomId(id)}>
      <h3>{t(title)}</h3>
      <div className={s.body}>{children}</div>
    </div>
  )
}

/** Kurze Rückmeldung neben einem Knopf („✓ gespeichert“); leer = unsichtbar. */
export function Note({ text }: { text: string }) {
  return <span className={`${s.saved} ${text ? s.on : ''}`}>{text}</span>
}

/** Protokoll eines Laufs; rollt beim Nachwachsen ans Ende. */
export function LogBox({ lines }: { lines: string[] }) {
  const ref = useRef<HTMLPreElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [lines])
  return (
    <pre ref={ref} className={s.log}>
      {lines.join('\n')}
    </pre>
  )
}
