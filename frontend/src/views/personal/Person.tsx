import type { CSSProperties } from 'react'
import type { Person } from '@/api/team'
import s from './Person.module.css'

/** Kleines Rundbild einer Person: ihr Foto oder der Anfangsbuchstabe in ihrer Farbe. */
export function Avatar({
  p,
  groesse = 34,
  aktiv = false,
}: {
  p: Pick<Person, 'name' | 'color' | 'avatar'>
  groesse?: number
  /** Pulsiert — „arbeitet gerade“. */
  aktiv?: boolean
}) {
  const farbe = p.color || '126,231,135'
  const stil: CSSProperties = {
    width: groesse,
    height: groesse,
    fontSize: groesse * 0.45,
    ['--accent-rgb' as string]: farbe,
    ...(p.avatar ? { backgroundImage: `url("${p.avatar}")` } : { background: `rgb(${farbe})` }),
  }
  return (
    <span className={`${s.avatar} ${aktiv ? s.aktiv : ''}`} style={stil}>
      {p.avatar ? '' : (p.name || '?')[0]?.toUpperCase()}
    </span>
  )
}
