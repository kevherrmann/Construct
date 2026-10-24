/** 2023-01-23 → 23.01.2023 (leer bleibt leer). */
export const datum = (iso: string | null | undefined) =>
  iso && /^\d{4}-\d{2}-\d{2}/.test(iso)
    ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`
    : ''

/** Tag-Eingabe: Komma oder Enter trennt, doppelte (ohne Groß/klein) fallen weg. */
export function tagsDazu(alt: string[], eingabe: string): string[] {
  const neu = eingabe
    .split(',')
    .map((x) => x.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
  const raus = [...alt]
  for (const n of neu) {
    if (!raus.some((r) => r.toLowerCase() === n.toLowerCase())) raus.push(n)
  }
  return raus
}

/** 2026-10-25T00:18:43 → 25.10.2026 00:18 */
export const zeitpunkt = (iso: string) =>
  iso ? `${datum(iso.slice(0, 10))} ${iso.slice(11, 16)}`.trim() : ''
