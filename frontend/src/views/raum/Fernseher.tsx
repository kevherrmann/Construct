import { useLayoutEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useChat } from '@/stores/chat'
import { befehleAus, useItems, useWerkstattDaten, type Befehl } from './daten'
import { viereckMatrix, type Viereck } from './kamera'
import { FERNSEHER, FERNSEHER_ZOOM } from './stationen'
import maske from './assets/fernseher-maske.webp'
import s from './Raum.module.css'

// Das Terminal läuft auf der Monitorwand selbst. Die Fläche ist ein normales
// Element in der Größe, die sie bei voller Kamerafahrt auf dem Bildschirm hat,
// perspektivisch auf die Wand gelegt (matrix3d). Aus der Nähe ist der Text
// gestochen scharf, aus der Ferne ein dichtes, leuchtendes Terminal im Raum.
//
// Nur solange etwas läuft, sonst der grüne Regen des Raumbilds. Ein Klick auf
// die Wand fährt durch den Bildschirm in die Chat-Ansicht; dabei leuchtet er
// voll auf (`voll`).

export function Fernseher({
  welt,
  voll = false,
  weich = false,
}: {
  welt: { w: number; h: number }
  voll?: boolean
  weich?: boolean
}) {
  const { t } = useTranslation()
  const items = useItems()
  const busy = useChat((st) => !!st.active()?.busy)
  const werkstatt = useWerkstattDaten()
  // Ganze Session aus dem Protokoll; was gerade erst losgeht, kennt es evtl.
  // noch nicht — das kommt aus dem Live-Stream dazu.
  const befehle = useMemo<Befehl[]>(() => {
    const live = befehleAus(items)
    const server = werkstatt?.befehle ?? []
    if (!server.length) return live
    const letzter = live[live.length - 1]
    if (busy && letzter && server[server.length - 1]?.command !== letzter.command)
      return [...server, letzter]
    return server
  }, [items, werkstatt, busy])
  const laeuftWas = busy && befehleAus(items).length > 0

  const liste = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = liste.current
    if (el) el.scrollTop = el.scrollHeight
  }, [befehle])

  if (!welt.w) return null
  const px = ([x, y]: readonly [number, number]) =>
    [(x * welt.w) / 100, (y * welt.h) / 100] as const
  const q: Viereck = [px(FERNSEHER[0]), px(FERNSEHER[1]), px(FERNSEHER[2]), px(FERNSEHER[3])]
  const breite = ((q[1][0] - q[0][0] + (q[2][0] - q[3][0])) / 2) * FERNSEHER_ZOOM
  const hoehe = ((q[3][1] - q[0][1] + (q[2][1] - q[1][1])) / 2) * FERNSEHER_ZOOM
  const an = voll || laeuftWas

  // Die Maske schneidet die Fläche genau auf die (gebogenen) Bildschirme zu.
  return (
    <div
      className={`${s.tvRahmen} ${weich ? s.weich : ''}`}
      style={{ maskImage: `url(${maske})`, WebkitMaskImage: `url(${maske})` }}
    >
      <div
        className={`${s.tv} ${an ? s.tvAn : ''}`}
        style={{ width: breite, height: hoehe, transform: viereckMatrix(breite, hoehe, q) }}
        aria-hidden
      >
        <div className={s.tvListe} ref={liste} data-scroll>
          <div className={s.tvKopf}>
            <b>TERMINAL</b>
            <span>
              {befehle.length} {t(befehle.length === 1 ? 'Befehl' : 'Befehle')}
            </span>
          </div>
          {!befehle.length && (
            <p className={s.tvLeer}>{t('In dieser Session lief noch kein Befehl.')}</p>
          )}
          {befehle.map((b, i) => (
            <div key={i} className={s.tvBefehl}>
              {b.description && <div className={s.tvZweck}># {b.description}</div>}
              <pre className={s.tvPrompt}>$ {b.command}</pre>
              {b.output !== null ? (
                <pre className={`${s.tvAusgabe} ${b.isError ? s.tvFehler : ''}`}>
                  {b.output.slice(-4000) || t('(keine Ausgabe)')}
                </pre>
              ) : (
                <div className={s.tvLaeuft}>▍</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
