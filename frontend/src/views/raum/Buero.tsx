import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BUERO_BUEHNE,
  DOPPEL,
  DOPPEL_HOEHE,
  PAARE,
  WERKBANK,
  WERKBANK_FUSS,
  type PaarId,
  type Platz,
} from './stationen'
import { WEG_MS, type Besuch, type BueroStand, type Sitz } from './useBuero'
import s from './Raum.module.css'

// Das Büro der Firma: in der freien Ecke links stehen zwei Doppelschreibtische, an
// jedem sitzen sich zwei Mitarbeiter gegenüber. Wer arbeitet, steht auf, geht nach
// vorn an die Werkbank und tippt dort wie der Assistent selbst; die Chefin schaut
// dabei kurz bei ihm vorbei. Die Bilder liegen unter /static/team/raum (mitgeliefert);
// wer keinen Doppelschreibtisch hat, steht mit seinem Profilbild am Rand.

const SPRITES = '/static/team/raum'

/** Wie viele am Tisch sitzen (Reihenfolge im Bild: links, rechts). */
type Belegung = 'beide' | 'links' | 'rechts' | 'leer'
const BELEGUNGEN: Belegung[] = ['beide', 'links', 'rechts', 'leer']
const anwesend = (b: Belegung) => (b === 'beide' ? 2 : b === 'leer' ? 0 : 1)

const prozent = (px: number, von: number) => `${(px / von) * 100}%`

/** Perspektive: wie groß eine Person bei Fußhöhe `y` ist, im Verhältnis zu der an der
 *  Werkbank (Horizont etwa bei y = 250 auf dem Raumbild). */
const HORIZONT = 250
const massstab = (y: number, bezug = WERKBANK_FUSS.y) => (y - HORIZONT) / (bezug - HORIZONT)

/** Position und Größe eines Tischbildes auf der Bühne (Prozent). */
function rahmen(p: Platz) {
  const k = (DOPPEL_HOEHE / DOPPEL.inhaltH) * p.s
  const w = DOPPEL.w * k
  const h = DOPPEL.h * k
  return {
    left: prozent(p.x - w / 2, BUERO_BUEHNE.w),
    top: prozent(p.y + DOPPEL.rand * k - h, BUERO_BUEHNE.h),
    width: prozent(w, BUERO_BUEHNE.w),
    height: prozent(h, BUERO_BUEHNE.h),
  }
}

/** Die Schreibtische samt Menschen, die Randplätze und die Wege zur Werkbank. */
export function Buero({
  stand,
  weich,
  onOeffnen,
}: {
  stand: BueroStand
  weich?: boolean
  onOeffnen: (slug: string) => void
}) {
  const an = (paar: PaarId, seite: 'links' | 'rechts') =>
    stand.leute.find((l) => l.paar === paar && l.seite === seite)
  // Hintere Tische zuerst zeichnen, damit die vorderen sie überdecken.
  const paare = (Object.keys(PAARE) as PaarId[]).sort((a, b) => PAARE[a].y - PAARE[b].y)
  return (
    <div className={`${s.buero} ${weich ? s.bueroWeich : ''}`}>
      {paare.map((id) => (
        <DoppelTisch
          key={id}
          platz={PAARE[id]}
          kennung={id}
          links={an(id, 'links')}
          rechts={an(id, 'rechts')}
          stand={stand}
          onOeffnen={onOeffnen}
        />
      ))}
      {stand.leute
        .filter((l) => !l.paar)
        .map((l) => (
          <Randplatz key={l.agent.slug} sitz={l} stand={stand} onOeffnen={onOeffnen} />
        ))}
      {stand.leute
        .filter((l) => l.paar)
        .map((l) => (
          <Laeufer key={l.agent.slug} sitz={l} da={stand.werk === l.agent.slug} />
        ))}
    </div>
  )
}

function DoppelTisch({
  platz,
  kennung,
  links,
  rechts,
  stand,
  onOeffnen,
}: {
  platz: Platz
  kennung: PaarId
  links?: Sitz
  rechts?: Sitz
  stand: BueroStand
  onOeffnen: (slug: string) => void
}) {
  const { t } = useTranslation()
  const da = (x?: Sitz) => !!x && stand.werk !== x.agent.slug
  const soll: Belegung =
    da(links) && da(rechts) ? 'beide' : da(links) ? 'links' : da(rechts) ? 'rechts' : 'leer'
  // Wer aufsteht, ist sofort vom Stuhl weg; wer zurückkommt, erst wenn er angekommen ist.
  const [gezeigt, setGezeigt] = useState<Belegung>(soll)
  useEffect(() => {
    if (soll === gezeigt) return
    const wartet = anwesend(soll) > anwesend(gezeigt) ? WEG_MS : 0
    const id = setTimeout(() => setGezeigt(soll), wartet)
    return () => clearTimeout(id)
  }, [soll, gezeigt])

  const knopf = (x: Sitz | undefined, seite: 'links' | 'rechts') =>
    x && (
      <button
        type="button"
        className={`${s.sitzKnopf} ${seite === 'links' ? s.sitzLinks : s.sitzRechts}`}
        onClick={() => onOeffnen(x.agent.slug)}
        aria-label={`${x.agent.name}, ${x.agent.title}`}
      >
        <span className={s.tischSchild}>
          <b>{x.agent.name}</b>
          <span>{stand.arbeiten.has(x.agent.slug) ? t('arbeitet gerade') : x.agent.title}</span>
        </span>
      </button>
    )
  const punkt = (x: Sitz | undefined, seite: 'links' | 'rechts') =>
    x &&
    stand.arbeiten.has(x.agent.slug) &&
    stand.werk !== x.agent.slug && (
      <i
        className={`${s.arbeitPunkt} ${seite === 'links' ? s.sitzLinks : s.sitzRechts}`}
        aria-hidden
      />
    )
  return (
    <div className={s.tisch} style={rahmen(platz)}>
      {BELEGUNGEN.map((b) => (
        <img
          key={b}
          src={`${SPRITES}/doppel-${kennung}-${b}.webp`}
          alt=""
          draggable={false}
          className={`${s.zustand} ${b === gezeigt ? s.zustandAn : ''}`}
        />
      ))}
      {punkt(links, 'links')}
      {punkt(rechts, 'rechts')}
      {knopf(links, 'links')}
      {knopf(rechts, 'rechts')}
    </div>
  )
}

/** Wer keinen Doppelschreibtisch hat: sein Profilbild steht am Rand; es leuchtet, wenn er arbeitet. */
function Randplatz({
  sitz,
  stand,
  onOeffnen,
}: {
  sitz: Sitz
  stand: BueroStand
  onOeffnen: (slug: string) => void
}) {
  const { t } = useTranslation()
  const { agent, platz } = sitz
  const d = 46 * platz.s * 1.2
  const arbeitet = stand.arbeiten.has(agent.slug)
  return (
    <button
      type="button"
      className={`${s.randplatz} ${arbeitet ? s.randArbeit : ''}`}
      style={{
        left: prozent(platz.x - d / 2, BUERO_BUEHNE.w),
        top: prozent(platz.y - d, BUERO_BUEHNE.h),
        width: prozent(d, BUERO_BUEHNE.w),
        height: prozent(d, BUERO_BUEHNE.h),
        ['--accent-rgb' as string]: agent.color,
      }}
      onClick={() => onOeffnen(agent.slug)}
      aria-label={`${agent.name}, ${agent.title}`}
    >
      {agent.avatar ? <img src={agent.avatar} alt="" draggable={false} /> : agent.name.slice(0, 1)}
      <span className={s.tischSchild}>
        <b>{agent.name}</b>
        <span>{arbeitet ? t('arbeitet gerade') : agent.title}</span>
      </span>
    </button>
  )
}

/** Die Figur an der Werkbank (Ebene wie die des Assistenten). Steht der Mitarbeiter
 *  nicht dort, liegt sie klein und unsichtbar an seinem Stuhl; der Wechsel ist der Weg. */
function Laeufer({ sitz, da }: { sitz: Sitz; da: boolean }) {
  // Verschiebung vom Werkbank-Fußpunkt zum Stuhl, in Prozent der Ebene selbst
  // (translate rechnet mit der eigenen Größe), und der Maßstab dort hinten.
  const lw = (WERKBANK.w / 100) * BUERO_BUEHNE.w
  const lh = (WERKBANK.h / 100) * BUERO_BUEHNE.h
  const dx = ((sitz.platz.x - WERKBANK_FUSS.x) / lw) * 100
  const dy = ((sitz.platz.y - WERKBANK_FUSS.y) / lh) * 100
  const k = massstab(sitz.platz.y)
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
      src={`${SPRITES}/${sitz.agent.slug}-werkbank.webp`}
      alt=""
      draggable={false}
    />
  )
}

/** Die Chefin auf dem Weg zu einem Sitz und zurück: dasselbe Standbild wie am Podest,
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
  const ziel = stand.leute.find((l) => l.agent.slug === besuch.slug)
  if (!ziel) return null
  // Sie stellt sich vor den Tisch neben den Stuhl, ein Stück näher am Betrachter.
  const seite = ziel.seite === 'rechts' ? 1 : -1
  const fuss = { x: ziel.platz.x + seite * 80 * ziel.platz.s, y: ziel.platz.y + 22 }
  const podestFuss = (podest.y / 100) * BUERO_BUEHNE.h
  const hh = podest.h * massstab(fuss.y, podestFuss)
  const hin = besuch.phase === 'hin'
  const x = hin ? (fuss.x / BUERO_BUEHNE.w) * 100 : podest.x
  const y = hin ? (fuss.y / BUERO_BUEHNE.h) * 100 : podest.y
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
