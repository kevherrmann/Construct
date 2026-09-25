// Kleine Formatierer für die Einstellungen.

/** Bytes als GB (mit Komma, eine Stelle) bzw. MB — wie in der alten Oberfläche. */
export const fmtGB = (n: number) =>
  n >= 1e9 ? (n / 1e9).toFixed(1).replace('.', ',') + ' GB' : Math.round((n || 0) / 1e6) + ' MB'

/** Prozent eines Fortschritts, 0 ohne bekannte Gesamtgröße. */
export const pct = (p: { total: number; completed: number }) =>
  p.total ? Math.round((p.completed / p.total) * 100) : 0

/**
 * Wie lange die letzte Update-Prüfung her ist: 'now' | {min} | {h}.
 * Getrennt vom Text, damit die Übersetzung die Zahl einsetzen kann.
 */
export function ago(lastCheck: number, now = Date.now() / 1000) {
  const min = Math.round((now - lastCheck) / 60)
  if (min < 1) return { unit: 'now' as const, n: 0 }
  if (min < 60) return { unit: 'min' as const, n: min }
  return { unit: 'h' as const, n: Math.round(min / 60) }
}
