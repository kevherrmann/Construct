import { Fragment, useEffect, useState, type CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import {
  formZellen,
  tetrisZiffern,
  zifferSteine,
  ZIFFER_BREITE,
  ZIFFER_HOEHE,
  type Stein,
  type Zelle,
} from './tetris'
import s from './Raum.module.css'
import { fxLevel } from '@/lib/fx'

// Tetris-Uhr: HH:MM aus fallenden Tetrominos. Beim Öffnen baut sich die Zeit
// einmal auf; wechselt danach eine Ziffer, verlischt nur sie und ihre Steine
// fallen neu. Die Sekunden lösen nichts aus. Der Fall geht wie im Spiel
// zeilenweise. Gedreht wird im sichtbaren Himmel über dem Raster: dort hält der
// Stein kurz an, dreht sich in seine Lage und fällt dann senkrecht ins Ziel.
// Alle Zeiten sind Vielfache von SCHRITT, so ändert sich das Bild nur im Takt.

const SCHRITT = 48 // ms je Zeile
const RAST = 2 * SCHRITT // Pause nach dem Einrasten, dann kommt der nächste Stein
const DREH = 3 // Schritte je Vierteldrehung
const HIMMEL = 2 // sichtbare Zeilen über dem Raster (Polster oben in .tetris)
const LEEREN = 8 * SCHRITT // so lange verlischt die alte Ziffer
const VERSATZ = 3 * SCHRITT // zwischen den Ziffern beim ersten Aufbau
const AUFTAKT = 14 * SCHRITT // bis die Ansicht eingeblendet ist (.projektion in Raum.module.css)

// Helligkeit (OKLCH) je Steinart: knapp abgestuft, damit man die Steine in der
// fertigen Ziffer erkennt, ohne dass die Ziffer fleckig wird.
const TON: Record<Stein['typ'], number> = {
  I: 0.7,
  O: 0.66,
  T: 0.69,
  S: 0.64,
  Z: 0.67,
  J: 0.62,
  L: 0.72,
}

const ZEILEN = Array.from({ length: ZIFFER_HOEHE }, (_, y) => y)
const SPALTEN = Array.from({ length: ZIFFER_BREITE }, (_, x) => x)

interface Bahn {
  start: number // ms nach Beginn der Ziffer
  schritte: number
  drehen: number[] // Lage je Drehstufe, die letzte ist die Ziellage
}

/** Wann welcher Stein fällt: einer nach dem anderen, jeder erst, wenn der vorige liegt.
 *  Ein Stein kommt von oberhalb des Sichtbaren (Unterkante HIMMEL + 1 über dem Raster),
 *  fällt bis knapp über das Raster, dreht dort und fällt dann bis ins Ziel. */
function fahrplan(steine: readonly Stein[]): { bahnen: Bahn[]; dauer: number } {
  let zeit = 0
  const bahnen = steine.map((st) => {
    // Erscheint in der Grundlage wie im Spiel und dreht auf kürzestem Weg.
    const drehen = st.drehung === 3 ? [0, 3] : Array.from({ length: st.drehung + 1 }, (_, i) => i)
    const hoehe = Math.max(...st.zellen.map((z) => z.y)) - st.y + 1
    const schritte = HIMMEL + (drehen.length - 1) * DREH + st.y + hoehe
    const bahn = { start: zeit, schritte, drehen }
    zeit += schritte * SCHRITT + RAST
    return bahn
  })
  return { bahnen, dauer: zeit }
}

/** Zellen des Steins nach `schritt` Zeilen Fall, im Raster der Ziffer (y < 0 liegt darüber). */
function imFall(st: Stein, bahn: Bahn, schritt: number): Zelle[] {
  const halt = HIMMEL // ab hier steht die Unterkante eine Zeile über dem Raster
  const stufe = Math.min(bahn.drehen.length - 1, Math.floor(Math.max(0, schritt - halt) / DREH))
  if (stufe === bahn.drehen.length - 1 && schritt >= halt)
    return st.zellen.map((z) => ({ x: z.x, y: z.y - (bahn.schritte - schritt) }))
  const unten = Math.min(schritt, halt) - HIMMEL - 1
  const form = formZellen(st.typ, bahn.drehen[stufe]!)
  const breite = Math.max(...form.map((z) => z.x)) + 1
  const hoehe = Math.max(...form.map((z) => z.y)) + 1
  const ziel = Math.max(...st.zellen.map((z) => z.x)) - st.x + 1
  const x = Math.min(ZIFFER_BREITE - breite, Math.max(0, st.x + Math.floor((ziel - breite) / 2)))
  return form.map((z) => ({ x: x + z.x, y: unten - hoehe + 1 + z.y }))
}

/** Eine Zelle; Kanten zu Nachbarn desselben Steins entfallen, so bleibt der Stein ein Stück. */
function Zellen({ zellen, ton }: { zellen: readonly Zelle[]; ton: number }) {
  const hat = (x: number, y: number) => zellen.some((z) => z.x === x && z.y === y)
  return zellen.map((z) => (
    <i
      key={`${z.x}.${z.y}`}
      style={
        {
          '--x': z.x,
          '--y': z.y,
          '--ton': ton,
          '--o': hat(z.x, z.y - 1) ? 0 : 1,
          '--r': hat(z.x + 1, z.y) ? 0 : 1,
          '--u': hat(z.x, z.y + 1) ? 0 : 1,
          '--l': hat(z.x - 1, z.y) ? 0 : 1,
        } as CSSProperties
      }
    />
  ))
}

interface Lauf {
  wert: number
  seit: number // ab hier fallen die Steine
  alt?: number // die verlöschende Ziffer davor
}

function Ziffer({ lauf, nun }: { lauf: Lauf; nun: number }) {
  const steine = zifferSteine(lauf.wert)
  const { bahnen } = fahrplan(steine)
  const t = nun - lauf.seit
  return (
    <div className={s.tetrisZiffer}>
      {ZEILEN.map((y) =>
        SPALTEN.map((x) => <b key={`${x}.${y}`} style={{ '--x': x, '--y': y } as CSSProperties} />),
      )}
      {lauf.alt !== undefined && t < 0 && (
        <div className={s.tetrisVerlischt}>
          {zifferSteine(lauf.alt).map((st, k) => (
            <Zellen key={k} zellen={st.zellen} ton={TON[st.typ]} />
          ))}
        </div>
      )}
      {steine.map((st, k) => {
        const bahn = bahnen[k]!
        const schritt = Math.floor((t - bahn.start) / SCHRITT)
        if (schritt < 0) return null
        const liegt = schritt >= bahn.schritte
        return (
          <div key={k} className={liegt ? s.tetrisLiegt : s.tetrisFaellt}>
            <Zellen zellen={liegt ? st.zellen : imFall(st, bahn, schritt)} ton={TON[st.typ]} />
          </div>
        )
      })}
    </div>
  )
}

const ruhig = () =>
  fxLevel() === 'off' || window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function TetrisUhr({ jetzt }: { jetzt: Date }) {
  const { t } = useTranslation()
  const werte = tetrisZiffern(jetzt).map((z) => z.wert)
  const schluessel = werte.join('')
  // Beim Öffnen fallen alle vier, leicht versetzt; mit reduzierter Bewegung liegen sie schon.
  const [laeufe, setLaeufe] = useState<Lauf[]>(() => {
    const ab = ruhig() ? -1e9 : performance.now() + AUFTAKT
    return werte.map((wert, i) => ({ wert, seit: ab + i * VERSATZ }))
  })
  const [nun, setNun] = useState(() => performance.now())

  // Neue Ziffern: nur die geänderten verlöschen und fallen neu.
  const [vorher, setVorher] = useState(schluessel)
  if (vorher !== schluessel) {
    setVorher(schluessel)
    setLaeufe((alt) => {
      const jetztMs = performance.now()
      const ab = ruhig() ? -1e9 : jetztMs + LEEREN
      return alt.map((l, i) => {
        if (l.wert === werte[i]) return l
        // Stand die alte Ziffer noch nicht (gerade erst geöffnet), verlischt nichts:
        // die neue baut sich einfach an ihrer Stelle auf.
        if (jetztMs < l.seit + fahrplan(zifferSteine(l.wert)).dauer)
          return { wert: werte[i]!, seit: Math.max(l.seit, jetztMs) }
        return { wert: werte[i]!, seit: ab, alt: l.wert }
      })
    })
  }

  // Solange etwas fällt, läuft die Anzeige mit, neu gezeichnet wird aber nur,
  // wenn eine Ziffer den nächsten Schritt erreicht; danach steht sie still.
  const ende = Math.max(...laeufe.map((l) => l.seit + fahrplan(zifferSteine(l.wert)).dauer))
  useEffect(() => {
    let id = 0
    let takt = ''
    const bild = () => {
      const jetztMs = performance.now()
      const neu = laeufe.map((l) => Math.floor((jetztMs - l.seit) / SCHRITT)).join()
      if (neu !== takt) {
        takt = neu
        setNun(jetztMs)
      }
      if (jetztMs < ende) id = requestAnimationFrame(bild)
    }
    id = requestAnimationFrame(bild)
    return () => cancelAnimationFrame(id)
  }, [laeufe, ende])

  const zeit = `${schluessel.slice(0, 2)}:${schluessel.slice(2)}`
  return (
    <div
      className={s.tetris}
      style={{ '--himmel': HIMMEL } as CSSProperties}
      role="img"
      aria-label={t('Tetris-Uhr: {zeit}', { zeit })}
    >
      <div className={s.tetrisBrett} aria-hidden="true">
        {laeufe.map((l, i) => (
          <Fragment key={i}>
            {i === 2 && (
              <div className={s.tetrisDoppelpunkt}>
                <i />
                <i />
              </div>
            )}
            <Ziffer lauf={l} nun={nun} />
          </Fragment>
        ))}
      </div>
    </div>
  )
}
