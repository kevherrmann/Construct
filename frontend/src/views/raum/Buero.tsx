import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BUERO_BUEHNE,
  BUERO_SPRITES,
  PAARE,
  WERKBANK,
  type PaarId,
  tischFlaeche,
  type Platz,
} from './stationen'
import { WEG_MS, type Besuch, type BueroStand, type Sitz } from './useBuero'
import { fxLevel } from '@/lib/fx'
import { PoseVideo } from './PoseVideo'
import s from './Raum.module.css'

// Das Büro der Firma: in der freien Ecke links stehen zwei Doppelschreibtische, an
// jedem sitzen sich zwei Mitarbeiter gegenüber. Wer arbeitet, steht auf, geht nach
// vorn an die Werkbank und tippt dort wie der Assistent selbst; die Chefin schaut
// dabei kurz bei ihm vorbei. Die Bilder liegen unter /static/team/raum (mitgeliefert);
// wer keinen Doppelschreibtisch hat, steht mit seinem Profilbild am Rand.

const SPRITES = BUERO_SPRITES
/** Tipp-Videos nur, wenn der Rechner Videos im Raum spielt (wie beim Assistenten). */
const VIDEO_AN = fxLevel() !== 'off'

/** Wie viele am Tisch sitzen (Reihenfolge im Bild: links, rechts). */
type Belegung = 'beide' | 'links' | 'rechts' | 'leer'
const BELEGUNGEN: Belegung[] = ['beide', 'links', 'rechts', 'leer']
const anwesend = (b: Belegung) => (b === 'beide' ? 2 : b === 'leer' ? 0 : 1)

const prozent = (px: number, von: number) => `${(px / von) * 100}%`

/** Perspektive: wie groß eine Person bei Fußhöhe `y` ist, im Verhältnis zu einer bei
 *  Fußhöhe `bezug`. Die Kamera schaut steil von oben, der Horizont liegt weit über dem Bild.
 *  Gemessen an den Tischbildern: wer dort sitzt, ist samt Stuhl knapp 290 px hoch,
 *  stehend also etwa 400 px, an der Werkbank 580 px. */
const HORIZONT = -700
const massstab = (y: number, bezug: number) => (y - HORIZONT) / (bezug - HORIZONT)

/** Position und Größe eines Tischbildes auf der Bühne (Prozent). */
function rahmen(p: Platz) {
  const r = tischFlaeche(p)
  return { left: `${r.l}%`, top: `${r.t}%`, width: `${r.w}%`, height: `${r.h}%` }
}

/** Die Schreibtische samt Menschen, die Randplätze und die Wege zur Werkbank. */
export function Buero({
  stand,
  weich,
  onOeffnen,
  onFokus,
}: {
  stand: BueroStand
  weich?: boolean
  onOeffnen: (slug: string) => void
  /** Maus oder Tastatur auf einem Platz: das Büro wird scharf gestellt. */
  onFokus: (an: boolean) => void
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
          onFokus={onFokus}
        />
      ))}
      {stand.leute
        .filter((l) => !l.paar)
        .map((l) => (
          <Randplatz
            key={l.agent.slug}
            sitz={l}
            stand={stand}
            onOeffnen={onOeffnen}
            onFokus={onFokus}
          />
        ))}
      {stand.leute
        .filter((l) => l.paar)
        .map((l) => (
          <Laeufer key={l.agent.slug} sitz={l} da={stand.werk === l.agent.slug} />
        ))}
    </div>
  )
}

const fokusGriffe = (onFokus: (an: boolean) => void) => ({
  onMouseEnter: () => onFokus(true),
  onMouseLeave: () => onFokus(false),
  onFocus: () => onFokus(true),
  onBlur: () => onFokus(false),
})

function DoppelTisch({
  platz,
  kennung,
  links,
  rechts,
  stand,
  onOeffnen,
  onFokus,
}: {
  platz: Platz
  kennung: PaarId
  links?: Sitz
  rechts?: Sitz
  stand: BueroStand
  onOeffnen: (slug: string) => void
  onFokus: (an: boolean) => void
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
        {...fokusGriffe(onFokus)}
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
  onFokus,
}: {
  sitz: Sitz
  stand: BueroStand
  onOeffnen: (slug: string) => void
  onFokus: (an: boolean) => void
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
      {...fokusGriffe(onFokus)}
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

/** Die Figur an der Werkbank (Ebene wie die des Assistenten). Vom Stuhl dorthin wird
 *  nicht gelaufen: er verschwindet am Tisch und erscheint an der Werkbank, wie der
 *  Assistent zwischen Podest und Werkbank. */
function Laeufer({ sitz, da }: { sitz: Sitz; da: boolean }) {
  // Angekommen: er tippt (Video über dem Standbild, wie beim Assistenten).
  const [angekommen, setAngekommen] = useState(false)
  useEffect(() => {
    if (!da) return
    const id = setTimeout(() => setAngekommen(true), WEG_MS)
    return () => {
      clearTimeout(id)
      setAngekommen(false)
    }
  }, [da])
  const datei = `${SPRITES}/${sitz.agent.slug}-tippen`
  return (
    <>
      <img
        className={`${s.laeufer} ${da ? s.laeuferDa : ''}`}
        style={{
          left: `${WERKBANK.l}%`,
          top: `${WERKBANK.t}%`,
          width: `${WERKBANK.w}%`,
          height: `${WERKBANK.h}%`,
        }}
        src={`${SPRITES}/${sitz.agent.slug}-werkbank.webp`}
        alt=""
        draggable={false}
      />
      {VIDEO_AN && (
        <PoseVideo
          clip={{ webm: `${datei}.webm`, mp4: `${datei}.mp4`, maske: `${datei}-maske.webp` }}
          ort={WERKBANK}
          an={da && angekommen}
        />
      )}
    </>
  )
}

/** Die Chefin am Tisch eines Mitarbeiters: dasselbe Standbild wie am Podest, nur
 *  kleiner, weil sie weiter hinten steht. Sie läuft nicht hin, sie blendet dort ein. */
export function Besucher({
  besuch,
  stand,
  bild,
  reden,
  podest,
}: {
  besuch: Besuch
  stand: BueroStand
  bild: string
  /** Seitlich im Gespräch (nach rechts gewandt); fehlt sie, bleibt das Standbild. */
  reden?: string
  podest: { x: number; y: number; h: number }
}) {
  const ziel = stand.leute.find((l) => l.agent.slug === besuch.slug)
  if (!ziel) return null
  // Sie stellt sich vor den Tisch neben den Stuhl, ein Stück näher am Betrachter.
  const seite = ziel.seite === 'rechts' ? 1 : -1
  const fuss = { x: ziel.platz.x + seite * 80 * ziel.platz.s, y: ziel.platz.y + 22 }
  const podestFuss = (podest.y / 100) * BUERO_BUEHNE.h
  const hh = podest.h * massstab(fuss.y, podestFuss)
  const da = besuch.phase === 'hin' || besuch.phase === 'da'
  // Am Tisch schaut sie den Mitarbeiter an: sitzt er rechts von ihr, wie im Bild,
  // sonst gespiegelt.
  const imGespraech = besuch.phase === 'da' && !!reden
  const x = (fuss.x / BUERO_BUEHNE.w) * 100
  const y = (fuss.y / BUERO_BUEHNE.h) * 100
  return (
    <img
      className={`${s.besucher} ${da ? s.besucherDa : ''} ${imGespraech && seite > 0 ? s.besucherLinks : ''}`}
      style={{ left: `${x}%`, top: `${y - hh}%`, height: `${hh}%` }}
      src={imGespraech ? reden : bild}
      alt=""
      draggable={false}
    />
  )
}
