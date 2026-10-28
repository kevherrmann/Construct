import { useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { UiSpec } from '@/lib/chat/genui'
import s from './GenUiChart.module.css'

type Spec = Extract<UiSpec, { type: 'chart' }>

const H = 180
const PAD = { top: 10, right: 12, bottom: 24, left: 40 }
const BAR_MAX = 24
const GAP = 2

/** Eine Reihe hat die Akzentfarbe des Themes; mehrere bekommen die geprüfte
 *  Reihenpalette (--viz-1 … --viz-4 in themes.css), immer in derselben Reihenfolge. */
const farbe = (i: number, n: number) => (n === 1 ? 'var(--green)' : `var(--viz-${i + 1})`)

/** Runde Achsenschritte: 1, 2 oder 5 mal einer Zehnerpotenz. */
function achse(min: number, max: number, ziel = 4) {
  if (min === max) max = min + 1
  const roh = (max - min) / ziel
  const pot = 10 ** Math.floor(Math.log10(roh))
  const schritt = ([1, 2, 5, 10].find((m) => m * pot >= roh) ?? 10) * pot
  const lo = Math.floor(min / schritt) * schritt
  const hi = Math.ceil(max / schritt) * schritt
  const ticks: number[] = []
  for (let v = lo; v <= hi + schritt / 2; v += schritt) ticks.push(+v.toFixed(10))
  return { lo, hi, ticks }
}

function useBreite() {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(480)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    if (el.clientWidth) setW(el.clientWidth)
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => e && setW(Math.round(e.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

export function Chart({ spec }: { spec: Spec }) {
  const { t, i18n } = useTranslation()
  const [ref, breite] = useBreite()
  const [idx, setIdx] = useState<number | null>(null)
  const [tabelle, setTabelle] = useState(false)
  const { labels, series, kind, unit } = spec
  const n = labels.length
  const ns = series.length

  const zahlFmt = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 2 })
  const kurzFmt = new Intl.NumberFormat(i18n.language, {
    notation: 'compact',
    maximumFractionDigits: 1,
  })
  const wert = (v: number | null) =>
    v === null ? '–' : `${zahlFmt.format(v)}${unit ? ` ${unit}` : ''}`

  const alle = series.flatMap((r) => r.values).filter((v): v is number => v !== null)
  // Balken wachsen von der Null aus; die Null gehört darum immer auf die Achse.
  const { lo, hi, ticks } = achse(Math.min(0, ...alle), Math.max(0, ...alle))
  const pw = Math.max(breite - PAD.left - PAD.right, 40)
  const ph = H - PAD.top - PAD.bottom
  const y = (v: number) => PAD.top + ph - ((v - lo) / (hi - lo)) * ph
  const band = pw / n
  const mitte = (i: number) => PAD.left + band * (i + 0.5)
  const balken = Math.min(BAR_MAX, (band * 0.75 - GAP * (ns - 1)) / ns)
  const gruppe = balken * ns + GAP * (ns - 1)
  // Beschriftungen unten so ausdünnen, dass keine sich überlappen.
  const jede = Math.max(1, Math.ceil(46 / band))

  const balkenPfad = (x: number, v: number) => {
    const y0 = y(0)
    const y1 = y(v)
    const r = Math.min(4, balken / 2, Math.abs(y0 - y1))
    const w = balken
    // Rund nur am Datenende, eckig an der Grundlinie.
    return v >= 0
      ? `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`
      : `M${x},${y0}V${y1 - r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 - r}V${y0}Z`
  }

  const linie = (werte: (number | null)[]) => {
    let d = ''
    let offen = false
    werte.forEach((v, i) => {
      if (v === null) {
        offen = false
        return
      }
      d += `${offen ? 'L' : 'M'}${mitte(i)},${y(v)}`
      offen = true
    })
    return d
  }

  // Tooltip neben die Stelle, nie darüber: sonst verdeckt er den Punkt, den man ansieht.
  const tipRechts = idx !== null && mitte(idx) < breite / 2

  return (
    <div className={s.chart}>
      <div className={s.kopf}>
        {spec.title && <div className={s.titel}>{spec.title}</div>}
        <button type="button" className={s.umschalter} onClick={() => setTabelle(!tabelle)}>
          {tabelle ? t('Diagramm') : t('Tabelle')}
        </button>
      </div>
      {ns > 1 && (
        <ul className={s.legende}>
          {series.map((r, i) => (
            <li key={i}>
              <span
                className={kind === 'line' ? s.keyLinie : s.keyFlaeche}
                style={{ background: farbe(i, ns) }}
              />
              {r.name}
            </li>
          ))}
        </ul>
      )}
      {tabelle ? (
        <div className={s.tabelleWrap}>
          <table className={s.tabelle}>
            <thead>
              <tr>
                <th />
                {series.map((r, i) => (
                  <th key={i}>{r.name || t('Wert')}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {labels.map((l, j) => (
                <tr key={j}>
                  <th>{l}</th>
                  {series.map((r, i) => (
                    <td key={i}>{wert(r.values[j] ?? null)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={ref} className={s.flaeche} onPointerLeave={() => setIdx(null)}>
          <svg width={breite} height={H} role="img" aria-label={spec.title || t('Diagramm')}>
            {ticks.map((v) => (
              <g key={v}>
                <line
                  className={v === 0 ? s.null : s.gitter}
                  x1={PAD.left}
                  x2={PAD.left + pw}
                  y1={y(v)}
                  y2={y(v)}
                />
                <text className={s.achse} x={PAD.left - 6} y={y(v)} dy="0.32em" textAnchor="end">
                  {Math.abs(v) >= 1000 ? kurzFmt.format(v) : zahlFmt.format(v)}
                </text>
              </g>
            ))}
            {labels.map((l, i) =>
              i % jede === 0 ? (
                <text key={i} className={s.achse} x={mitte(i)} y={H - 6} textAnchor="middle">
                  {l.length > 10 ? `${l.slice(0, 9)}…` : l}
                </text>
              ) : null,
            )}
            {kind === 'line' && idx !== null && (
              <line
                className={s.fadenkreuz}
                x1={mitte(idx)}
                x2={mitte(idx)}
                y1={PAD.top}
                y2={PAD.top + ph}
              />
            )}
            {kind === 'bar'
              ? series.map((r, i) =>
                  r.values.map((v, j) =>
                    v === null || v === 0 ? null : (
                      <path
                        key={`${i}-${j}`}
                        className={`${s.balken} ${idx === j ? s.aktiv : ''}`}
                        d={balkenPfad(mitte(j) - gruppe / 2 + i * (balken + GAP), v)}
                        style={{ fill: farbe(i, ns) }}
                      />
                    ),
                  ),
                )
              : series.map((r, i) => (
                  <g key={i}>
                    <path
                      className={s.linie}
                      d={linie(r.values)}
                      style={{ stroke: farbe(i, ns) }}
                    />
                    {r.values.map((v, j) =>
                      v !== null && (j === idx || n === 1) ? (
                        <circle
                          key={j}
                          className={s.punkt}
                          cx={mitte(j)}
                          cy={y(v)}
                          r={4}
                          style={{ fill: farbe(i, ns) }}
                        />
                      ) : null,
                    )}
                  </g>
                ))}
            {/* Trefferflächen: ganze Spalte je Stelle, größer als jede Markierung. */}
            {labels.map((l, j) => (
              <rect
                key={j}
                className={s.treffer}
                x={PAD.left + band * j}
                y={PAD.top}
                width={band}
                height={ph}
                tabIndex={0}
                aria-label={`${l}: ${series.map((r) => `${ns > 1 && r.name ? `${r.name} ` : ''}${wert(r.values[j] ?? null)}`).join(', ')}`}
                onPointerEnter={() => setIdx(j)}
                onFocus={() => setIdx(j)}
                onBlur={() => setIdx(null)}
              />
            ))}
          </svg>
          {idx !== null && (
            <div
              className={`${s.tip} ${tipRechts ? '' : s.tipLinks}`}
              style={{ left: mitte(idx) + (tipRechts ? 10 : -10) }}
              aria-hidden
            >
              <div className={s.tipLabel}>{labels[idx]}</div>
              {series.map((r, i) => (
                <div key={i} className={s.tipZeile}>
                  <span className={s.keyLinie} style={{ background: farbe(i, ns) }} />
                  <b>{wert(r.values[idx] ?? null)}</b>
                  {ns > 1 && <span className={s.tipName}>{r.name}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
