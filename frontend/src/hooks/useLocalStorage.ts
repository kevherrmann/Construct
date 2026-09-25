import { useCallback, useState } from 'react'

// localStorage kann in manchen WebViews fehlen oder werfen (Private Mode,
// strenge Einstellungen) — dann gilt der Wert eben nur für diese Sitzung.
function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function useLocalStorage(key: string): [string | null, (v: string | null) => void] {
  const [value, setValue] = useState(() => read(key))
  const set = useCallback(
    (v: string | null) => {
      setValue(v)
      try {
        if (v === null) window.localStorage.removeItem(key)
        else window.localStorage.setItem(key, v)
      } catch {
        /* siehe oben */
      }
    },
    [key],
  )
  return [value, set]
}
