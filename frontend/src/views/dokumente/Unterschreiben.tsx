import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  dateiUrl,
  seiteUrl,
  unterschriftUrl,
  useDokumenteAktionen,
  useSeiten,
  type Dok,
  type Element,
} from '@/api/dokumente'
import { UnterschriftPad } from './UnterschriftPad'
import { ortDatum, ortHolen, ortMerken, vergroessert, verschoben } from './unterschrift'
import s from './Dokumente.module.css'

interface Props {
  d: Dok
  onFertig: (neu: Dok) => void
  onZu: () => void
}

type Griff = { i: number; art: 'ziehen' | 'groesse'; x: number; y: number } | null

// Unterschrift (und auf Wunsch „Ort, Datum“) auf die Seiten legen. Das Ergebnis
// wird ein neues Dokument; das Original bleibt, wie es war.
export function Unterschreiben({ d, onFertig, onZu }: Props) {
  const { t } = useTranslation()
  const act = useDokumenteAktionen()
  const { data, isError } = useSeiten(d.id)
  const seiten = data?.seiten ?? []
  // null = letzte Seite: dort wird meist unterschrieben
  const [wahl, setN] = useState<number | null>(null)
  const n = wahl ?? Math.max(1, seiten.length)
  const [elemente, setElemente] = useState<Element[]>([])
  const [gewaehlt, setGewaehlt] = useState<number | null>(null)
  const [pad, setPad] = useState(false)
  const [sigV, setSigV] = useState(0)
  const [sigVerh, setSigVerh] = useState(0.35)
  const [ohneBild, setOhneBild] = useState<Set<number>>(new Set())
  const [fehler, setFehler] = useState('')
  const [ergebnis, setErgebnis] = useState<Dok | null>(null)
  const blatt = useRef<HTMLDivElement | null>(null)
  const [blattBreite, setBlattBreite] = useState(0)
  const griff = useRef<Griff>(null)
  // Unterschrift aus der Vorschau aufs Blatt ziehen. Bewusst mit Zeiger-
  // Ereignissen statt HTML-Drag&Drop: ein gezogenes <img> wird im Browser zur
  // Datei, und die nehmen Chat und Dokumente-Ablage als Upload an.
  const [schweben, setSchweben] = useState<{
    x: number
    y: number
    start: { x: number; y: number }
  } | null>(null)

  const hatSig = !!data?.unterschrift || sigV > 0
  useEffect(() => {
    const b = blatt.current
    if (!b) return
    const ro = new ResizeObserver(() => setBlattBreite(b.clientWidth))
    ro.observe(b)
    return () => ro.disconnect()
  }, [data])

  const seite = seiten[n - 1] ?? { breite: 595, hoehe: 842 }
  const blattHoehe = (blattBreite * seite.hoehe) / seite.breite

  const dazu = (e: Element) => {
    setElemente((alt) => [...alt, e])
    setGewaehlt(elemente.length)
  }
  const aendern = (i: number, e: Element) =>
    setElemente((alt) => alt.map((x, j) => (j === i ? e : x)))
  const weg = (i: number) => {
    setElemente((alt) => alt.filter((_, j) => j !== i))
    setGewaehlt(null)
  }

  const runter = (e: PointerEvent, i: number, art: 'ziehen' | 'groesse') => {
    e.stopPropagation()
    e.preventDefault()
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    griff.current = { i, art, x: e.clientX, y: e.clientY }
    setGewaehlt(i)
  }
  const ziehen = (e: PointerEvent) => {
    const g = griff.current
    const el = g ? elemente[g.i] : undefined
    if (!g || !el || !blattBreite) return
    const dx = (e.clientX - g.x) / blattBreite
    const dy = (e.clientY - g.y) / blattHoehe
    griff.current = { ...g, x: e.clientX, y: e.clientY }
    aendern(g.i, g.art === 'ziehen' ? verschoben(el, dx, dy) : vergroessert(el, dx, seite))
  }
  const los = () => (griff.current = null)

  const sigNeu = (mitte?: { x: number; y: number }): Element => {
    const breite = 0.3
    const hoehe = (breite * seite.breite * sigVerh) / seite.hoehe
    if (!mitte)
      return { art: 'unterschrift', seite: n, x: 0.55, y: Math.min(0.78, 0.97 - hoehe), breite }
    return verschoben(
      { art: 'unterschrift', seite: n, x: 0, y: 0, breite },
      mitte.x - breite / 2,
      mitte.y - hoehe / 2,
    )
  }
  const ablegen = (e: PointerEvent) => {
    const sw = schweben
    setSchweben(null)
    if (!sw) return
    // Nur geklickt, nicht gezogen: wie „+ Unterschrift“
    if (Math.hypot(e.clientX - sw.start.x, e.clientY - sw.start.y) < 5) return dazu(sigNeu())
    const r = blatt.current?.getBoundingClientRect()
    if (
      !r ||
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      return
    dazu(sigNeu({ x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }))
  }

  const fertig = async () => {
    setFehler('')
    try {
      const neu = await act.unterschreiben.mutateAsync({ id: d.id, elemente })
      ortMerken(elemente)
      setErgebnis(neu)
    } catch (e) {
      setFehler((e as Error).message)
    }
  }

  const gw = gewaehlt !== null ? elemente[gewaehlt] : undefined

  if (ergebnis) {
    return (
      <div className={s.form}>
        <div className={s.status}>
          ✓ {t('Unterschrieben und abgelegt als „{t}“.', { t: ergebnis.titel })}
        </div>
        <p className={s.erklaer}>{t('Das Original bleibt unverändert in der Ablage.')}</p>
        <div className={s.aktionen}>
          <a className={`${s.knopf} ${s.voll}`} href={dateiUrl(ergebnis.id, true)} download>
            {t('⬇ HERUNTERLADEN')}
          </a>
          <button type="button" className={s.knopf} onClick={() => onFertig(ergebnis)}>
            {t('ZUM NEUEN DOKUMENT')}
          </button>
          <button type="button" className={s.knopf} onClick={onZu}>
            {t('ZURÜCK')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className={s.detail} onDragStart={(e) => e.preventDefault()}>
      <div>
        {isError && <div className={s.fehler}>{t('Die Seiten lassen sich nicht lesen.')}</div>}
        {seiten.length > 1 && (
          <div className={s.blaettern}>
            <button
              type="button"
              className={s.zurueck}
              disabled={n <= 1}
              onClick={() => setN(n - 1)}
            >
              ‹
            </button>
            {t('Seite {n} von {m}', { n, m: seiten.length })}
            <button
              type="button"
              className={s.zurueck}
              disabled={n >= seiten.length}
              onClick={() => setN(n + 1)}
            >
              ›
            </button>
          </div>
        )}
        <div
          ref={blatt}
          className={s.blatt}
          style={{
            aspectRatio: `${seite.breite} / ${seite.hoehe}`,
            // Ganze Seite sichtbar, auch über der Eingabezeile des Chats
            maxWidth: `calc((100vh - 330px) * ${seite.breite / seite.hoehe})`,
          }}
          onPointerDown={() => setGewaehlt(null)}
          onPointerMove={ziehen}
          onPointerUp={los}
          onPointerCancel={los}
        >
          {data && !ohneBild.has(n) && (
            <img
              key={n}
              src={seiteUrl(d.id, n)}
              alt=""
              draggable={false}
              onError={() => setOhneBild(new Set(ohneBild).add(n))}
            />
          )}
          {elemente.map((e, i) =>
            e.seite !== n ? null : (
              <div
                key={i}
                className={`${s.stempel} ${gewaehlt === i ? s.gewaehlt : ''}`}
                style={{
                  left: `${e.x * 100}%`,
                  top: `${e.y * 100}%`,
                  ...(e.art === 'unterschrift'
                    ? { width: `${e.breite * 100}%` }
                    : { fontSize: `${e.hoehe * blattHoehe}px` }),
                }}
                onPointerDown={(ev) => runter(ev, i, 'ziehen')}
              >
                {e.art === 'unterschrift' ? (
                  <img src={unterschriftUrl(sigV)} alt={t('Unterschrift')} draggable={false} />
                ) : (
                  <span className={s.stempeltext}>{e.text || '…'}</span>
                )}
                {gewaehlt === i && (
                  <>
                    <button
                      type="button"
                      className={s.stempelweg}
                      title={t('entfernen')}
                      onPointerDown={(ev) => ev.stopPropagation()}
                      onClick={() => weg(i)}
                    >
                      ✕
                    </button>
                    <span
                      className={s.stempelgriff}
                      title={t('Größe ändern')}
                      onPointerDown={(ev) => runter(ev, i, 'groesse')}
                    />
                  </>
                )}
              </div>
            ),
          )}
        </div>
        {ohneBild.has(n) && (
          <div className={s.leise}>
            {t('Ohne Ghostscript gibt es keine Seitenansicht. Platzieren geht trotzdem.')}
          </div>
        )}
      </div>
      <div className={s.form}>
        <div className={s.lbl}>{t('UNTERSCHRIFT')}</div>
        {hatSig ? (
          <div className={s.sigvorschau}>
            <img
              src={unterschriftUrl(sigV)}
              alt={t('Unterschrift')}
              title={t('Auf die Seite ziehen')}
              draggable={false}
              onPointerDown={(e) => {
                e.preventDefault()
                e.currentTarget.setPointerCapture(e.pointerId)
                const p = { x: e.clientX, y: e.clientY }
                setSchweben({ ...p, start: p })
              }}
              onPointerMove={(e) =>
                schweben && setSchweben({ ...schweben, x: e.clientX, y: e.clientY })
              }
              onPointerUp={ablegen}
              onPointerCancel={() => setSchweben(null)}
              onLoad={(e) =>
                setSigVerh(e.currentTarget.naturalHeight / e.currentTarget.naturalWidth || 0.35)
              }
            />
            <button type="button" className={s.link} onClick={() => setPad(true)}>
              {t('ändern')}
            </button>
          </div>
        ) : (
          <p className={s.erklaer}>
            {t('Noch keine Unterschrift hinterlegt. Einmal zeichnen, dann steht sie immer bereit.')}
          </p>
        )}
        <div className={s.aktionen}>
          {hatSig ? (
            <button type="button" className={s.knopf} onClick={() => dazu(sigNeu())}>
              {t('+ UNTERSCHRIFT')}
            </button>
          ) : (
            <button type="button" className={`${s.knopf} ${s.voll}`} onClick={() => setPad(true)}>
              {t('UNTERSCHRIFT ZEICHNEN')}
            </button>
          )}
          <button
            type="button"
            className={s.knopf}
            onClick={() =>
              dazu({
                art: 'text',
                seite: n,
                x: 0.1,
                y: 0.8,
                hoehe: 11 / seite.hoehe,
                text: ortDatum(ortHolen()),
              })
            }
          >
            {t('+ ORT, DATUM')}
          </button>
        </div>
        {gw?.art === 'text' && gewaehlt !== null && (
          <label className={s.feldbox}>
            <span className={s.lbl}>{t('TEXT')}</span>
            <input
              className={s.feld}
              value={gw.text}
              maxLength={120}
              autoFocus
              onChange={(e) => aendern(gewaehlt, { ...gw, text: e.target.value })}
            />
          </label>
        )}
        <p className={s.leise}>
          {elemente.length
            ? t('Zum Verschieben ziehen, Größe am Griff unten rechts.')
            : t('Zieh die Unterschrift aus der Vorschau auf die Seite.')}
        </p>
        {fehler && <div className={s.fehler}>{fehler}</div>}
        <div className={s.aktionen}>
          <button
            type="button"
            className={`${s.knopf} ${s.voll}`}
            disabled={!elemente.length || act.unterschreiben.isPending}
            onClick={() => void fertig()}
          >
            {act.unterschreiben.isPending ? '…' : t('✓ UNTERSCHREIBEN')}
          </button>
          <button type="button" className={s.knopf} onClick={onZu}>
            {t('ABBRECHEN')}
          </button>
        </div>
      </div>
      {schweben && (
        <img
          className={s.schweben}
          src={unterschriftUrl(sigV)}
          alt=""
          style={{ left: schweben.x, top: schweben.y, width: 0.3 * (blattBreite || 300) }}
        />
      )}
      <UnterschriftPad
        open={pad}
        onClose={() => setPad(false)}
        onGespeichert={() => setSigV((v) => v + 1)}
      />
    </div>
  )
}
