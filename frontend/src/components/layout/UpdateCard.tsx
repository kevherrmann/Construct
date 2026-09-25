import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { apiGet } from '@/lib/api'
import { useUpdateCard } from '@/stores/updateCard'
import s from './UpdateCard.module.css'

type StepState = 'idle' | 'run' | 'ok' | 'new' | 'error' | 'skip'
interface UpdateStatus {
  running: boolean
  done: boolean
  changed: boolean
  steps: Record<string, { state: StepState; msg?: string; to?: string }>
  log: string[]
}

// Kurz nach dem Laden schneller nachfragen: der Start-Lauf braucht einen
// Moment, bis er überhaupt als "läuft" erscheint.
const eagerUntil = Date.now() + 25000

const NAMES: Record<string, string> = { claude: 'Claude Code', hermes: 'Hermes' }
const ICON: Record<StepState, string> = {
  run: '⟳',
  ok: '✓',
  new: '✓',
  error: '⚠',
  skip: '–',
  idle: '·',
}

// Der Server sucht beim Start selbst nach neuen Fassungen (updates.py); hier
// wird das nur sichtbar gemacht — eine Karte, die sich von allein wieder
// verabschiedet, wenn nichts war.
export function UpdateCard() {
  const { t } = useTranslation()
  // Einmal laufen gesehen? Nur dann gibt es etwas zu melden — eine längst
  // abgeschlossene Prüfung soll nicht bei jedem Neuladen wieder auftauchen.
  const { hidden, seen, hide } = useUpdateCard()
  // Welcher abgeschlossene Lauf schon ausgeblendet wurde (Länge des Logs als Kennung).
  const [fadedAt, setFadedAt] = useState(-1)
  const q = useQuery({
    queryKey: ['updates'],
    queryFn: async () => {
      const d = await apiGet<UpdateStatus>('/api/updates')
      if (d.running) useUpdateCard.getState().markSeen()
      return d
    },
    refetchInterval: (query) =>
      query.state.data?.running ? 1200 : Date.now() < eagerUntil ? 1500 : 60000,
  })
  const st = q.data
  const steps = st?.steps ?? {}
  const shown = Object.keys(NAMES).filter((k) => steps[k] && steps[k]!.state !== 'idle')
  const bad = shown.some((k) => steps[k]!.state === 'error')

  const runKey = st?.log?.length ?? 0
  // Gute Nachricht = kurze Nachricht. Neuerungen und Fehler bleiben stehen.
  useEffect(() => {
    if (!st?.done || st.running || st.changed || bad) return
    const id = setTimeout(() => setFadedAt(runKey), 3500)
    return () => clearTimeout(id)
  }, [st?.done, st?.running, st?.changed, bad, runKey])

  const faded = !st?.running && fadedAt === runKey
  if (!st || hidden || faded || !(st.running || (seen && st.done))) return null

  const text = (k: string) => {
    const x = steps[k]!
    if (x.state === 'new') return x.msg || t('aktualisiert')
    if (x.state === 'ok') return t('aktuell') + (x.to ? ` · ${x.to}` : '')
    if (x.state === 'error') return x.msg || t('Fehler')
    if (x.state === 'skip') return x.msg || t('übersprungen')
    if (x.state === 'run') return t('prüfe …')
    return ''
  }
  const title = st.running
    ? t('WERKZEUGE PRÜFEN')
    : bad
      ? t('UPDATE FEHLGESCHLAGEN')
      : st.changed
        ? t('AKTUALISIERT')
        : t('ALLES AKTUELL')

  return (
    <div className={s.card}>
      <h4>
        <span className={st.running ? s.spin : ''}>{st.running ? '⟳' : bad ? '⚠' : '✓'}</span>
        <span>{title}</span>
        <button type="button" className={s.x} title={t('ausblenden')} onClick={hide}>
          ✕
        </button>
      </h4>
      {shown.length ? (
        shown.map((k) => (
          <div key={k} className={`${s.row} ${s[steps[k]!.state] ?? ''}`}>
            <span className={steps[k]!.state === 'run' ? s.spin : ''}>{ICON[steps[k]!.state]}</span>
            <span className={s.n}>{NAMES[k]}</span>
            <span className={s.v}>{text(k)}</span>
          </div>
        ))
      ) : (
        <div className={s.row}>
          <span className={s.n}>{t('suche …')}</span>
        </div>
      )}
      <div className={s.line}>
        {st.done && st.changed
          ? t('wirkt ab dem nächsten Chat')
          : ((st.log ?? []).slice(-1)[0] ?? '')}
      </div>
    </div>
  )
}
