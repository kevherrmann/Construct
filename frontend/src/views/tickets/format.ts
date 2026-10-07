/** Der Link in den Verlauf, optional zu einer Nachricht. */
export const chatLink = (t: { session: string; project: string }, cwd: string, msg?: string) =>
  `/chat?session=${encodeURIComponent(t.session)}&project=${encodeURIComponent(t.project)}` +
  `&cwd=${encodeURIComponent(cwd)}${msg ? `&msg=${encodeURIComponent(msg)}` : ''}`

/** Ordnername, den Claude Code für einen Arbeitsordner anlegt (/home/k/p → -home-k-p). */
export const transkriptOrdner = (cwd: string) => cwd.replace(/[^A-Za-z0-9]/g, '-')

/** "07.10. 14:32" aus einem ISO-Zeitstempel ohne Zone ("2026-10-07T14:32:03"). */
export const kurzzeit = (ts: string) =>
  ts.length >= 16 ? `${ts.slice(8, 10)}.${ts.slice(5, 7)}. ${ts.slice(11, 16)}` : ''
