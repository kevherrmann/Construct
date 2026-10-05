import { useEffect, useState } from 'react'

/** Wartezeit bis zur nächsten vollen Sekunde (ms), mit kleinem Polster. */
export const bisVolleSekunde = (ms = Date.now()) => 1000 - (ms % 1000) + 5

/**
 * Aktuelle Zeit, die genau zur vollen Sekunde weiterspringt — nicht eine
 * Sekunde nach dem Öffnen. So stimmen Anzeige und Ticken (lib/klang.ts)
 * überein, und alle Uhren im Raum springen gleichzeitig.
 */
export function useSekunde(): Date {
  const [jetzt, setJetzt] = useState(() => new Date())
  useEffect(() => {
    let id: ReturnType<typeof setTimeout>
    const weiter = () => {
      id = setTimeout(() => {
        setJetzt(new Date())
        weiter()
      }, bisVolleSekunde())
    }
    weiter()
    return () => clearTimeout(id)
  }, [])
  return jetzt
}
