import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { runUpdates, updatesState, type UpdateState } from '@/api/settings'
import { usePolling } from '@/hooks/usePolling'
import { ago } from '@/lib/format'
import { rich } from '@/lib/rich'
import { trServer } from '@/lib/serverText'
import { useSettings } from '@/stores/settings'
import { useUpdateCard } from '@/stores/updateCard'
import { LogBox, Note, Section } from './parts'
import s from './Settings.module.css'

const lastChecked = (t: TFunction, ts: number) => {
  const a = ago(ts)
  if (a.unit === 'now') return t('zuletzt gerade eben geprüft')
  if (a.unit === 'min') return t('zuletzt vor {n} min geprüft', { n: a.n })
  return t('zuletzt vor {n} h geprüft', { n: a.n })
}

// Dieselbe Quelle wie die Karte unten rechts, nur ausführlicher: hier steht
// das ganze Protokoll, und der Lauf lässt sich von Hand anstoßen.
export function UpdatesSection() {
  const { t } = useTranslation()
  const upd = useSettings((st) => st.settings.updates)
  const save = useSettings((st) => st.save)
  const [running, setRunning] = useState(false)
  const [log, setLog] = useState<string[] | null>(null)
  const [note, setNote] = useState('')

  // Läuft gerade schon einer (etwa der vom Start), gleich mitzeigen.
  useEffect(() => {
    let alive = true
    updatesState()
      .then((st) => {
        if (!alive) return
        if (st.log?.length) setLog(st.log)
        if (st.running) setRunning(true)
        else if (st.last_check) setNote(lastChecked(t, st.last_check))
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [t])

  usePolling(running, updatesState, (st: UpdateState) => {
    setLog(st.log ?? [])
    if (!st.done) return
    setRunning(false)
    const bad = Object.values(st.steps ?? {}).some((x) => x.state === 'error')
    setNote(
      bad ? t('⚠ mit Fehlern beendet') : st.changed ? t('✓ aktualisiert') : t('✓ alles aktuell'),
    )
  })

  const now = async () => {
    setRunning(true)
    setNote('')
    setLog([])
    let r: Awaited<ReturnType<typeof runUpdates>> = {}
    try {
      r = await runUpdates()
    } catch {
      /* wie die alte Oberfläche: trotzdem beobachten */
    }
    if (r.ok === false) {
      setRunning(false)
      setNote('⚠ ' + (trServer(r.error) || t('nicht gestartet')))
      return
    }
    // Karte unten rechts wieder zeigen, auch wenn sie weggeklickt war.
    useUpdateCard.getState().reveal()
  }

  return (
    <Section id="updates">
      <div className={s.row}>
        <label>
          <input
            type="checkbox"
            checked={upd?.auto !== false}
            onChange={(e) => void save({ updates: { auto: e.target.checked } })}
          />
          <span>
            <span className={s.t}>{t('Beim Start nach Updates suchen')}</span>
            <span className={s.d}>
              {rich(
                t(
                  'Holt neue Fassungen von <b>Claude Code</b> und <b>Hermes</b>, sobald CONSTRUCT hochfährt — im Hintergrund, der Chat bleibt bedienbar. Ohne das bleiben beide auf dem Stand von damals: ihre eigene Selbstaktualisierung ist ab Werk abgeschaltet.',
                ),
              )}
            </span>
          </span>
        </label>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Wie oft höchstens')}</span>
          <span className={s.d}>
            {t('Verhindert, dass fünf Neustarts an einem Nachmittag fünf Netzrunden auslösen.')}
          </span>
          <span className={s.actions}>
            <select
              className={s.btn}
              value={String(upd?.interval_h ?? 6)}
              onChange={(e) => void save({ updates: { interval_h: +e.target.value } })}
            >
              <option value="0">{t('bei jedem Start')}</option>
              <option value="6">{t('höchstens alle 6 Stunden')}</option>
              <option value="24">{t('höchstens einmal am Tag')}</option>
              <option value="168">{t('höchstens einmal die Woche')}</option>
            </select>
            <button type="button" className={s.btn} disabled={running} onClick={() => void now()}>
              {running ? t('läuft…') : t('Jetzt suchen')}
            </button>
            <Note text={note} />
          </span>
          {log && <LogBox lines={log} />}
        </span>
      </div>
    </Section>
  )
}
