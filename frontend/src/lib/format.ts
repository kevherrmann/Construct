export const baseName = (p?: string | null) =>
  (p ?? '').split('/').filter(Boolean).pop() || p || '?'

export const fmtNum = (n?: number | null) =>
  n == null
    ? '?'
    : n >= 1000
      ? (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, '') + 'k'
      : String(n)

export function fmtDur(ms?: number | null) {
  if (ms == null) return '?'
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} s`
  return `${Math.floor(s / 60)} m ${Math.round(s % 60)} s`
}

export const isPdf = (u?: string) => /\.pdf$/i.test(u ?? '')
