// localStorage kann in manchen WebViews fehlen oder werfen (Private Mode,
// strenge Einstellungen) — dann gilt der Wert eben nur für diese Sitzung.
export function getItem(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function setItem(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    /* siehe oben */
  }
}
