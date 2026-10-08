import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import { useTeamStand } from '@/api/team'
import { useLiveZug } from '@/components/firma/useLiveZug'
import { RUHIG, useMedien } from '@/hooks/useMedien'
import { useFx } from '@/lib/fx'
import { PLUS_ORT, brust, nebenMitarbeiter, wartende, type Holo, type Stellung } from './hologramme'
import { BUERO_BUEHNE, BUERO_SPRITES, WERKBANK } from './stationen'
import type { BueroStand, Sitz } from './useBuero'
import s from './Raum.module.css'
import { useHologramme } from './useHologramme'

// Helfer als Hologramme: eine grün leuchtende Kopie der Figur baut sich aus
// Scanlinien neben ihr auf, geht an die Station ihres Werkzeugs und zerfällt am
// Ende in Code-Regen; ein Blatt schwebt zum Besitzer zurück. Welche wo stehen,
// rechnet hologramme.ts aus, hier wird nur gezeichnet.

/** Sparmodus und „Bewegung reduzieren“: nur weich ein- und ausblenden. */
function useRuhig() {
  const fx = useFx()
  const reduziert = useMedien(RUHIG)
  return fx !== 'full' || reduziert
}

/** Bilder einer Figur für ihre Hologramme. */
export interface HoloBilder {
  idle: string
  lesen: string
  werkbank: string
}

const pct = (n: number) => `${n}%`

/** Lage und Bild einer Stellung; Kopf und Figurbreite für Schild und Code-Regen. */
function ansicht(st: Stellung, bilder: HoloBilder) {
  if (st.art === 'pose')
    return {
      bild: bilder[st.pose],
      stil: { left: pct(st.x), top: pct(st.y - st.h), height: pct(st.h) } as CSSProperties,
      klasse: s.holoPose,
      kopf: { x: st.x, y: st.y - st.h * 0.985 },
      fuss: st.y,
    }
  const r = st.r
  return {
    bild: bilder.werkbank,
    stil: { left: pct(r.l), top: pct(r.t), width: pct(r.w), height: pct(r.h) } as CSSProperties,
    klasse: s.holoWerk,
    kopf: { x: r.l + r.w * (355 / 768), y: r.t + r.h * (62 / 832) },
    fuss: r.t + r.h * (626 / 832),
  }
}

/** Form der Figur, durchzogen von Zeilen, durch die der Raum scheint. */
const maske = (bild: string) =>
  `url(${bild}), repeating-linear-gradient(to bottom, #000 0 2px, rgba(0, 0, 0, 0.45) 2px 4px)`

const schluessel = (st: Stellung) =>
  st.art === 'pose' ? `p:${st.pose}:${st.x}:${st.y}` : `w:${st.r.l}:${st.r.t}`

/** Zeichen des Code-Regens: Ziffern und ein paar Halbbreiten-Katakana wie im Matrix-Regen. */
const ZEICHEN = '01ｱｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾂﾃﾅﾆﾇﾈﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾗﾘﾜ'
function spalten(id: string, n: number): string[] {
  // aus der id gewürfelt: dieselbe Figur zerfällt bei jedem Zeichnen gleich
  let x = [...id].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7)
  const zufall = () => (x = (x * 1103515245 + 12345) >>> 0) / 2 ** 32
  return Array.from({ length: n }, () =>
    Array.from({ length: 9 }, () => ZEICHEN[Math.floor(zufall() * ZEICHEN.length)]).join(''),
  )
}

/** Ein Hologramm. Wechselt die Stellung (andere Station), blendet es dort aus und
 *  hier ein; beim ersten Erscheinen baut es sich von den Füßen her auf. */
function Hologramm({
  holo,
  stellung,
  bilder,
  ziel,
  ruhig,
}: {
  holo: Holo
  stellung: Stellung
  bilder: HoloBilder
  /** Brust des Besitzers: dorthin schwebt am Ende das Blatt. */
  ziel: { x: number; y: number }
  ruhig: boolean
}) {
  const k = schluessel(stellung)
  const [war, setWar] = useState<{ k: string; st: Stellung } | null>(null)
  const [jetzt, setJetzt] = useState({ k, st: stellung })
  if (jetzt.k !== k) {
    setWar(jetzt)
    setJetzt({ k, st: stellung })
  }
  useEffect(() => {
    if (!war) return
    const id = setTimeout(() => setWar(null), 500)
    return () => clearTimeout(id)
  }, [war])
  // Nur die erste Stellung baut sich auf; jede weitere blendet ein.
  const [erste] = useState(k)
  const phase = holo.phase
  const a = ansicht(jetzt.st, bilder)
  const rede = spalten(holo.id, 11)
  const gestalt = (st: Stellung, rolle: 'da' | 'geht') => {
    const v = ansicht(st, bilder)
    const auf = rolle === 'da' && phase === 'erscheint' && schluessel(st) === erste
    return (
      <div
        key={schluessel(st)}
        className={[
          s.holo,
          v.klasse,
          ruhig ? s.holoRuhig : '',
          rolle === 'geht' ? s.holoGeht : auf ? s.holoAuf : s.holoKommt,
          rolle === 'da' && phase === 'zerfaellt' ? s.holoZerfall : '',
          rolle === 'da' && phase === 'flackert' ? s.holoFlackert : '',
        ].join(' ')}
        style={v.stil}
        aria-hidden
      >
        <div
          className={s.holoKoerper}
          style={{ maskImage: maske(v.bild), WebkitMaskImage: maske(v.bild) }}
        >
          <img src={v.bild} alt="" draggable={false} />
          <i className={s.holoTon} />
          <i className={s.holoLinien} />
          <i className={s.holoScan} />
        </div>
        {rolle === 'da' && phase === 'zerfaellt' && !ruhig && (
          <div className={s.holoRegen}>
            {rede.map((z, i) => (
              <span key={i} style={{ ['--i' as string]: i }}>
                {z}
              </span>
            ))}
          </div>
        )}
      </div>
    )
  }
  const von = brust(jetzt.st)
  const mitte = { x: (von.x + ziel.x) / 2, y: Math.min(von.y, ziel.y) - 7 }
  const schild = phase === 'erscheint' || phase === 'arbeitet'
  // Ganz oben im Raum (hinten im Büro) wäre das Schild abgeschnitten: dann unter die
  // Füße. Nebeneinander stehen die Schilder abwechselnd höher, sonst laufen sie ineinander.
  const unten = a.kopf.y < 9
  const hoch = jetzt.st.art === 'pose' && holo.ort === 'neben' && holo.platz % 2 === 1
  const schildOrt = unten ? { x: a.kopf.x, y: a.fuss } : a.kopf
  return (
    <>
      {war && gestalt(war.st, 'geht')}
      {gestalt(jetzt.st, 'da')}
      {holo.beschreibung && (
        <Schild
          key={`schild:${jetzt.k}`}
          className={`${s.holoSchild} ${unten ? s.holoSchildUnten : hoch ? s.holoSchildHoch : ''} ${schild ? '' : s.holoSchildWeg}`}
          left={pct(schildOrt.x)}
          top={pct(schildOrt.y)}
        >
          <b>{holo.beschreibung}</b>
          {holo.detail && <span>{holo.detail}</span>}
        </Schild>
      )}
      {phase === 'zerfaellt' && !ruhig && (
        <i
          className={s.holoBlatt}
          style={
            {
              '--x0': pct(von.x),
              '--y0': pct(von.y),
              '--xm': pct(mitte.x),
              '--ym': pct(mitte.y),
              '--x1': pct(ziel.x),
              '--y1': pct(ziel.y),
            } as CSSProperties
          }
          aria-hidden
        />
      )}
    </>
  )
}

/** Abstand des Schilds zum Bildrand (px). */
const RAND = 8

/** Schild über dem Kopf. Ragt es aus dem Bild (auf dem Handy steht das Hologramm
 *  am Rand des Panoramas), rückt es ganz hinein; die Linie zeigt weiter auf den Kopf.
 *  Ist der Kopf selbst außer Sicht, verschwindet es, statt allein am Rand zu hängen.
 *  Folgt dem Wischen. */
function Schild({
  className,
  left,
  top,
  children,
}: {
  className: string
  left: string
  top: string
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    // steht schon von einem früheren Durchgang am Element
    let schub = parseFloat(el.style.getPropertyValue('--schieben')) || 0
    let bild = 0
    const messen = () => {
      bild = 0
      const r = el.getBoundingClientRect()
      // Kamera-Zoom: Bildschirm-Pixel ↔ Pixel im Raum
      const zoom = el.offsetWidth ? r.width / el.offsetWidth : 1
      const links = r.left - schub * zoom
      const rechts = links + r.width
      const kopf = links + r.width / 2
      el.style.visibility = kopf < 0 || kopf > innerWidth ? 'hidden' : ''
      const noetig =
        links < RAND ? RAND - links : rechts > innerWidth - RAND ? innerWidth - RAND - rechts : 0
      const neu = noetig / zoom
      if (Math.abs(neu - schub) < 0.5) return
      schub = neu
      el.style.setProperty('--schieben', `${neu}px`)
    }
    const spaeter = () => {
      if (!bild) bild = requestAnimationFrame(messen)
    }
    messen()
    addEventListener('scroll', spaeter, true)
    addEventListener('resize', spaeter)
    const ro = new ResizeObserver(spaeter)
    ro.observe(el)
    return () => {
      removeEventListener('scroll', spaeter, true)
      removeEventListener('resize', spaeter)
      ro.disconnect()
      cancelAnimationFrame(bild)
    }
  }, [left, top])
  return (
    <div ref={ref} className={className} style={{ left, top }} aria-hidden>
      {children}
    </div>
  )
}

/** Alle Hologramme eines Besitzers samt „+N“ für die, die keinen Platz haben. */
export function HoloSchicht({
  holos,
  stellungen,
  bilder,
  ziel,
  plus,
}: {
  holos: readonly Holo[]
  stellungen: ReadonlyMap<string, Stellung>
  bilder: HoloBilder
  ziel: { x: number; y: number }
  /** Wo „+N“ steht (Prozent); ohne: gleich neben dem letzten. */
  plus?: { x: number; y: number }
}) {
  const ruhig = useRuhig()
  const n = wartende(holos)
  return (
    <>
      {holos.map((h) => {
        const st = stellungen.get(h.id)
        return (
          st && (
            <Hologramm
              key={h.id}
              holo={h}
              stellung={st}
              bilder={bilder}
              ziel={ziel}
              ruhig={ruhig}
            />
          )
        )
      })}
      {n > 0 && (
        <span
          className={s.holoPlus}
          style={{ left: pct((plus ?? PLUS_ORT).x), top: pct((plus ?? PLUS_ORT).y) }}
          aria-hidden
        >
          +{n}
        </span>
      )}
    </>
  )
}

/** Die Hologramme eines Mitarbeiters: sein Bild von der Werkbank, neben ihm. */
function MitarbeiterHolos({ sitz, run, amWerk }: { sitz: Sitz; run: string; amWerk: boolean }) {
  const { lauf } = useLiveZug(run)
  const holos = useHologramme(lauf.helfer, run)
  const stellungen = useMemo(() => {
    const m = new Map<string, Stellung>()
    for (const h of holos)
      if (h.platz >= 0) m.set(h.id, { art: 'werkbank', r: nebenMitarbeiter(amWerk, sitz, h.platz) })
    return m
  }, [holos, amWerk, sitz])
  const bild = `${BUERO_SPRITES}/${sitz.agent.slug}-werkbank.webp`
  const ziel = amWerk
    ? brust({ art: 'werkbank', r: WERKBANK })
    : {
        x: (sitz.platz.x / BUERO_BUEHNE.w) * 100,
        y: ((sitz.platz.y - 150 * sitz.platz.s) / BUERO_BUEHNE.h) * 100,
      }
  const letzte = nebenMitarbeiter(amWerk, sitz, 3)
  return (
    <HoloSchicht
      holos={holos}
      stellungen={stellungen}
      bilder={{ idle: bild, lesen: bild, werkbank: bild }}
      ziel={ziel}
      plus={{ x: letzte.l + letzte.w * 0.6, y: letzte.t + letzte.h * 0.2 }}
    />
  )
}

/** Hologramme aller Mitarbeiter, die gerade arbeiten (ohne die Chefin: ihre stehen
 *  am Podest bei der Figur). */
export function BueroHologramme({ stand }: { stand: BueroStand }) {
  const { data } = useTeamStand()
  return (
    <>
      {(data?.aktiv ?? []).map((z) => {
        const sitz = stand.leute.find((l) => l.agent.slug === z.agent)
        return (
          sitz &&
          z.run && (
            <MitarbeiterHolos
              key={z.agent}
              sitz={sitz}
              run={z.run}
              amWerk={stand.werk === z.agent}
            />
          )
        )
      })}
    </>
  )
}
