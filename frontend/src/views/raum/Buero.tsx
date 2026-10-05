import { useTranslation } from 'react-i18next'
import { BUERO_BUEHNE, BUERO_FUSS, WERKBANK, WERKBANK_FUSS, type Platz } from './stationen'
import type { Besuch, BueroStand } from './useBuero'
import s from './Raum.module.css'

// Das Büro der Firma: hinten im Raum sitzt jeder Mitarbeiter an seinem Schreibtisch.
// Wer arbeitet, steht auf, geht nach vorn an die Werkbank und tippt dort wie der
// Assistent selbst; die Chefin schaut dabei kurz bei ihm vorbei. Die Sprites liegen
// unter /static/team/raum (mitgeliefert); wer keine hat, bekommt den leeren Tisch mit
// seinem Profilbild auf dem Stuhl.

const SPRITES = '/static/team/raum'
/** Für diese Mitarbeiter gibt es Bilder von Tisch und Werkbank. */
const MIT_BILD = new Set(['cody', 'selma', 'tessa', 'veritas'])

// Der Tisch wird aus einem 410 × 500 px großen Bild gezeichnet (Tisch 370 × 460,
// 20 px Rand für den Standschatten); Fußpunkt = vorderste Ecke des Tisches.
const TISCH = { w: 410, h: 500, rand: 20, inhalt: 460 }

const prozent = (px: number, von: number) => `${(px / von) * 100}%`

/** Position und Größe eines Tischbildes auf der Bühne (Prozent). */
function tischRahmen(p: Platz) {
  const k = (BUERO_FUSS / TISCH.inhalt) * p.s
  const w = TISCH.w * k
  const h = TISCH.h * k
  return {
    left: prozent(p.x - w / 2, BUERO_BUEHNE.w),
    top: prozent(p.y + TISCH.rand * k - h, BUERO_BUEHNE.h),
    width: prozent(w, BUERO_BUEHNE.w),
    height: prozent(h, BUERO_BUEHNE.h),
  }
}

/** Die Schreibtische samt Menschen und die Wege zur Werkbank. */
export function Buero({
  stand,
  weich,
  onOeffnen,
}: {
  stand: BueroStand
  weich?: boolean
  onOeffnen: (slug: string) => void
}) {
  const { t } = useTranslation()
  // Hintere Tische zuerst zeichnen, damit die vorderen sie überdecken.
  const reihen = [...stand.plaetze].sort((a, b) => a.platz.y - b.platz.y)
  return (
    <div className={`${s.buero} ${weich ? s.bueroWeich : ''}`}>
      {reihen.map(({ agent, platz }) => {
        const bild = MIT_BILD.has(agent.slug)
        const amWerk = stand.werk === agent.slug
        const arbeitet = stand.arbeiten.has(agent.slug)
        return (
          <div key={agent.slug} className={s.tisch} style={tischRahmen(platz)}>
            <img src={`${SPRITES}/tisch-leer.webp`} alt="" draggable={false} />
            {bild ? (
              <img
                src={`${SPRITES}/${agent.slug}-tisch.webp`}
                alt=""
                draggable={false}
                className={`${s.sitzt} ${amWerk ? s.sitztWeg : ''}`}
              />
            ) : (
              <span
                className={`${s.stuhlBild} ${amWerk ? s.sitztWeg : ''}`}
                style={{ ['--accent-rgb' as string]: agent.color }}
              >
                {agent.avatar ? (
                  <img src={agent.avatar} alt="" draggable={false} />
                ) : (
                  agent.name.slice(0, 1)
                )}
              </span>
            )}
            {arbeitet && !amWerk && <i className={s.tischArbeit} aria-hidden />}
            <button
              type="button"
              className={s.tischKnopf}
              onClick={() => onOeffnen(agent.slug)}
              aria-label={`${agent.name}, ${agent.title}`}
            >
              <span className={s.tischSchild}>
                <b>{agent.name}</b>
                <span>{arbeitet ? t('arbeitet gerade') : agent.title}</span>
              </span>
            </button>
          </div>
        )
      })}
      {stand.plaetze
        .filter(({ agent }) => MIT_BILD.has(agent.slug))
        .map(({ agent, platz }) => (
          <Laeufer
            key={agent.slug}
            slug={agent.slug}
            platz={platz}
            da={stand.werk === agent.slug}
          />
        ))}
    </div>
  )
}

/** Die Figur an der Werkbank (Ebene wie die des Assistenten). Steht der Mitarbeiter
 *  nicht dort, liegt sie klein und unsichtbar an seinem Tisch; der Wechsel ist der Weg. */
function Laeufer({ slug, platz, da }: { slug: string; platz: Platz; da: boolean }) {
  // Verschiebung vom Werkbank-Fußpunkt zum Tisch, in Prozent der Ebene selbst
  // (translate rechnet mit der eigenen Größe), und der Maßstab dort hinten.
  const lw = (WERKBANK.w / 100) * BUERO_BUEHNE.w
  const lh = (WERKBANK.h / 100) * BUERO_BUEHNE.h
  const dx = ((platz.x - WERKBANK_FUSS.x) / lw) * 100
  const dy = ((platz.y - 10 * platz.s - WERKBANK_FUSS.y) / lh) * 100
  const k = 0.3 * platz.s
  return (
    <img
      className={`${s.laeufer} ${da ? s.laeuferDa : ''}`}
      style={{
        left: `${WERKBANK.l}%`,
        top: `${WERKBANK.t}%`,
        width: `${WERKBANK.w}%`,
        height: `${WERKBANK.h}%`,
        ['--von' as string]: `translate(${dx}%, ${dy}%) scale(${k})`,
      }}
      src={`${SPRITES}/${slug}-werkbank.webp`}
      alt=""
      draggable={false}
    />
  )
}

/** Die Chefin auf dem Weg zu einem Tisch und zurück: dasselbe Standbild wie am Podest,
 *  nur kleiner, je weiter hinten sie steht. */
export function Besucher({
  besuch,
  stand,
  bild,
  podest,
}: {
  besuch: Besuch
  stand: BueroStand
  bild: string
  podest: { x: number; y: number; h: number }
}) {
  const ziel = stand.plaetze.find((p) => p.agent.slug === besuch.slug)?.platz
  if (!ziel) return null
  // Sie stellt sich links neben den Tisch, ein Stück näher am Betrachter.
  const fx = ((ziel.x - 150 * ziel.s) / BUERO_BUEHNE.w) * 100
  const fy = ((ziel.y + 14) / BUERO_BUEHNE.h) * 100
  const hh = podest.h * 0.36 * ziel.s
  const hin = besuch.phase === 'hin'
  const x = hin ? fx : podest.x
  const y = hin ? fy : podest.y
  const h = hin ? hh : podest.h
  return (
    <img
      className={`${s.besucher} ${besuch.phase === 'start' ? s.besucherStart : ''}`}
      style={{ left: `${x}%`, top: `${y - h}%`, height: `${h}%` }}
      src={bild}
      alt=""
      draggable={false}
    />
  )
}
