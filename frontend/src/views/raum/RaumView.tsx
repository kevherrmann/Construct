import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useTranslation } from 'react-i18next'
import { useSessions } from '@/api/chat'
import { useProviders } from '@/api/providers'
import { useVersion } from '@/api/system'
import { Composer } from '@/components/chat/Composer'
import { BeendenKnopf } from '@/components/layout/Beenden'
import type { PickerName } from '@/components/chat/Pickers'
import { Markdown } from '@/components/chat/Markdown'
import { baseName } from '@/lib/format'
import { MODES, modelInfo } from '@/lib/chat/models'
import { fxLevel } from '@/lib/fx'
import { KOMPAKT, useMedien } from '@/hooks/useMedien'
import { useChat } from '@/stores/chat'
import { useSettings } from '@/stores/settings'
import { useUi } from '@/stores/ui'
import { usePersonal } from '@/views/personal/store'
import { ChatView } from '@/views/chat/ChatView'
import raumBild from './assets/raum.webp'
import codyIdle from './assets/cody-idle.webp'
import codyDenken from './assets/cody-denken.webp'
import codyLesen from './assets/cody-lesen.webp'
import codyErklaeren from './assets/cody-erklaeren.webp'
import codyWerkbank from './assets/cody-werkbank.webp'
import codyReden from './assets/cody-reden.webp'
import geraeteBild from './assets/werkbank-geraete.webp'
import unscharfBild from './assets/raum-unscharf.webp'
import klemmbrettBild from './assets/klemmbrett.webp'
import kastenBild from './assets/kasten.webp'
import postkorbBild from './assets/postkorb.webp'
import { abschnitte, lageAus, type Phase } from './lage'
import { KartenInhalt } from './RaumKarten'
import { useRaumKlang } from './useRaumKlang'
import { Fernseher } from './Fernseher'
import { RegalSchild, WandBinaeruhr, WandKontingent } from './Raumdetails'
import { Besucher, Buero } from './Buero'
import { useBuero } from './useBuero'
import { useTeamBlase } from './useTeamBlase'
import { useTeamStand } from '@/api/team'
import { useAuftraegeAnsicht } from '../auftraege/store'
import { aufBuehne, GANZ, weltTransform, type Kamera, type Punkt } from './kamera'
import {
  BUERO_FORM,
  AUFTRITT,
  EINTAUCHEN,
  FIGUR,
  KLEMMBRETT,
  PODEST_VIDEO,
  SCHEIN_RAND,
  STATIONEN,
  FORM,
  KASTEN,
  POSTKORB,
  WERKBANK,
  type Ansicht,
  type Auftritt,
  type PanelId,
  type Rechteck,
  type StationId,
  VIELECK,
} from './stationen'
import { PoseVideo, type Clip } from './PoseVideo'
import s from './Raum.module.css'

/** 'arbeiten' ist keine Pose am Podest: dafür geht die Figur an die Werkbank
 *  und tippt dort an der Tastatur (statt in die Luft). */
type Pose = 'idle' | 'denken' | 'lesen' | 'arbeiten' | 'erklaeren'
type PodestPose = Exclude<Pose, 'arbeiten'>
const POSEN: PodestPose[] = ['idle', 'denken', 'lesen', 'erklaeren']

interface Figur {
  /** 'cody' oder 'eigen' (static/figur dieser Installation). */
  name: string
  posen: Record<PodestPose, string>
  /** Figur an der Werkbank (Ausschnitt WERKBANK). */
  werkbank: string
  /** Im Gespräch am Schreibtisch eines Mitarbeiters: seitlich, nach rechts gewandt
   *  (gespiegelt, wenn er links von ihr sitzt). Fehlt sie, steht dort das Standbild. */
  reden?: string
  /** Schleifen je Pose: am Podest im Ausschnitt PODEST_VIDEO, 'arbeiten' an
   *  der Werkbank im Ausschnitt WERKBANK. Fehlt eine, bleibt das Standbild. */
  videos: Partial<Record<Pose, Clip>>
}

// assets/video/<figur>-<pose>.webm|mp4 und <figur>-<pose>-maske.webp
const VIDEO_DATEI = import.meta.glob<string>('./assets/video/*', {
  eager: true,
  import: 'default',
})
function videosVon(datei: (pfad: string) => string | undefined): Figur['videos'] {
  const out: Figur['videos'] = {}
  for (const p of [...POSEN, 'arbeiten'] as Pose[]) {
    const d = (endung: string) => datei(`${p}${endung}`)
    const webm = d('.webm')
    const mp4 = d('.mp4')
    const maske = d('-maske.webp')
    if (webm && mp4 && maske) out[p] = { webm, mp4, maske }
  }
  return out
}

// Im Raum steht Cody. Alle Posen liegen auf gleicher Leinwand, Fußpunkt unten
// in der Mitte — ein Wechsel springt nicht.
const CODY: Figur = {
  name: 'cody',
  posen: { idle: codyIdle, denken: codyDenken, lesen: codyLesen, erklaeren: codyErklaeren },
  werkbank: codyWerkbank,
  reden: codyReden,
  videos: videosVon((d) => VIDEO_DATEI[`./assets/video/cody-${d}`]),
}

/** Eigene Figur einer Installation statt Cody: liegt in static/figur
 *  (gitignored), der Server gibt die Dateiliste beim Start mit. Gleiche
 *  Leinwand wie Cody. Pflicht: idle, denken, lesen, erklaeren, werkbank (.webp).
 *  Freiwillig: reden.webp (im Gespräch am Schreibtisch, seitlich nach rechts) und
 *  video/<pose>.webm|mp4 + video/<pose>-maske.webp. Monitor, Tastatur,
 *  unscharfer Raum und die Werkbank-Masken gehören zum Raum und sind für alle Figuren
 *  gleich (frühere Dateien werkbank-geraete, raum-unscharf, form-/schein-werkbank
 *  werden nicht mehr gebraucht). Fehlt etwas Pflicht, bleibt es bei Cody. */
function eigeneFigur(dateien: string[]): Figur | null {
  const da = new Set(dateien)
  const url = (d: string) => (da.has(d) ? `/static/figur/${d}` : undefined)
  const bild = (n: string) => url(`${n}.webp`)
  const [idle, denken, lesen, erklaeren, werkbank] = [
    'idle',
    'denken',
    'lesen',
    'erklaeren',
    'werkbank',
  ].map(bild)
  if (!idle || !denken || !lesen || !erklaeren || !werkbank) return null
  return {
    name: 'eigen',
    posen: { idle, denken, lesen, erklaeren },
    werkbank,
    reden: bild('reden'),
    videos: videosVon((d) => url(`video/${d}`)),
  }
}

// Form jeder Station als Maske: beim Überfahren bleibt sie scharf.
const FORM_BILD = import.meta.glob<string>('./assets/form/*.webp', {
  eager: true,
  import: 'default',
})

// Hover-Variante je nach Leistung: Mit voller Optik stellt die Kamera auf das
// Objekt scharf (der Rest wird unscharf). Im Sparmodus (Software-Rendering)
// wäre das zäh — dort bekommt das Objekt nur einen weichen Schein.
const SCHEIN = fxLevel() !== 'full'
const SCHEIN_BILD = import.meta.glob<string>('./assets/schein/*.webp', {
  eager: true,
  import: 'default',
})

/** Bild aus form/ bzw. schein/ (die Werkbank heißt dort `werkbank-cody.webp`).
 *  Was nicht im Raumbild gemalt ist (die Binäruhr), hat stattdessen ein Vieleck. */
function bildVon(ordner: 'form' | 'schein', id: StationId) {
  const alle = ordner === 'form' ? FORM_BILD : SCHEIN_BILD
  const datei = alle[`./assets/${ordner}/${id}-cody.webp`] ?? alle[`./assets/${ordner}/${id}.webp`]
  const vieleck = VIELECK[id]
  return datei ?? (vieleck && vieleckBild(vieleck, FORM[id], ordner === 'schein'))
}

/** Vieleck (Prozent der Fläche `f`) als Maskenbild; als Schein weich und mit dem
 *  Rand der Schein-Masken drumherum. */
function vieleckBild(form: readonly Punkt[], f: Rechteck, schein: boolean) {
  const rx = schein ? (SCHEIN_RAND.x / f.w) * 100 : 0
  const ry = schein ? (SCHEIN_RAND.y / f.h) * 100 : 0
  const sx = 100 / (100 + 2 * rx)
  const sy = 100 / (100 + 2 * ry)
  const punkte = form.map(([x, y]) => `${((x + rx) * sx).toFixed(2)},${((y + ry) * sy).toFixed(2)}`)
  const weich = schein ? '<filter id="w"><feGaussianBlur stdDeviation="3"/></filter>' : ''
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" preserveAspectRatio="none">${weich}` +
    `<polygon points="${punkte.join(' ')}" fill="#fff"${schein ? ' filter="url(#w)"' : ''}/></svg>`
  return `"data:image/svg+xml,${encodeURIComponent(svg)}"`
}

/** Maske „alles außer dieser Station“ für Unschärfe und Schleier. Das Büro hat
 *  keine Form im Raumbild: dort sind es die Schreibtische samt Leuten. */
function ohneStation(id: StationId | null): React.CSSProperties {
  const formen =
    id === 'firma'
      ? BUERO_FORM
      : id && bildVon('form', id)
        ? [{ bild: bildVon('form', id)!, flaeche: FORM[id] }]
        : []
  if (!formen.length) return {}
  // background-position in %: Versatz = (Fläche − Bild) · p
  const lage = ({ l, t, w, h }: Rechteck) =>
    `${w >= 100 ? 0 : (l / (100 - w)) * 100}% ${h >= 100 ? 0 : (t / (100 - h)) * 100}%`
  const m = {
    image: [...formen.map((f) => `url(${f.bild})`), 'linear-gradient(#000 0 0)'].join(', '),
    size: [...formen.map((f) => `${f.flaeche.w}% ${f.flaeche.h}%`), '100% 100%'].join(', '),
    position: [...formen.map((f) => lage(f.flaeche)), '0 0'].join(', '),
  }
  // Jede Form wird aus der vollen Fläche darunter ausgeschnitten (sie überlappen nicht).
  const aus = (op: string) => formen.map(() => op).join(', ')
  return {
    maskImage: m.image,
    maskSize: m.size,
    maskPosition: m.position,
    maskRepeat: 'no-repeat',
    maskComposite: aus('exclude'),
    WebkitMaskImage: m.image,
    WebkitMaskSize: m.size,
    WebkitMaskPosition: m.position,
    WebkitMaskRepeat: 'no-repeat',
    WebkitMaskComposite: aus('xor'),
  }
}

const platz = (r: Rechteck) => ({
  left: `${r.l}%`,
  top: `${r.t}%`,
  width: `${r.w}%`,
  height: `${r.h}%`,
})

/** Jede Pose bleibt mindestens so lange stehen — sonst zappelt die Figur,
 *  wenn Text und Werkzeuge im Sekundentakt wechseln. */
const POSE_MIN_MS = 1200
/** Kurzes Nachdenken zwischen zwei Werkzeugen holt die Figur nicht jedes Mal
 *  von der Werkbank zurück: erst wenn es so lange dauert, geht sie zum Podest. */
const WERKBANK_HALTEN_MS = 2500

// Sparmodus "aus": keine Videos, nur Standbilder mit Überblendung.
const VIDEO_AN = fxLevel() !== 'off'

function useRuhigePose(ziel: Pose): Pose {
  const [pose, setPose] = useState(ziel)
  const seit = useRef(0) // 0 = noch nie gewechselt, also sofort
  useEffect(() => {
    if (ziel === pose) return
    const halten = pose === 'arbeiten' && ziel === 'denken' ? WERKBANK_HALTEN_MS : 0
    const warten = Math.max(halten, POSE_MIN_MS - (Date.now() - seit.current))
    const id = setTimeout(() => {
      seit.current = Date.now()
      setPose(ziel)
    }, warten)
    return () => clearTimeout(id)
  }, [ziel, pose])
  return pose
}

const POSE_VON: Record<Phase, Pose> = {
  ruht: 'idle',
  denkt: 'denken',
  wartet: 'denken',
  liest: 'lesen',
  sucht: 'lesen',
  recherchiert: 'lesen',
  schreibt: 'arbeiten',
  terminal: 'arbeiten',
  werkzeug: 'arbeiten',
  delegiert: 'arbeiten',
  antwortet: 'erklaeren',
}

const TITEL: Record<Ansicht, string> = {
  protokoll: 'Protokoll',
  uhr: 'Uhr',
  projekte: 'Projekte',
  sessions: 'Sessions',
  kalender: 'Kalender',
  skills: 'Skills',
  mcp: 'MCP',
  werkbank: 'Werkbank',
  mail: 'E-Mails',
  ausruestung: 'Modell & Modus',
  tickets: 'Tickets',
  personal: 'Personal',
  auftraege: 'Aufträge',
  einstellungen: 'Einstellungen',
}

// Statuszeile der Sprechblase; {d} = Datei, Befehl, Suchbegriff …
const PHASE_TEXT: Record<Phase, string> = {
  ruht: '',
  denkt: 'denkt nach …',
  liest: 'liest {d}',
  sucht: 'sucht {d}',
  schreibt: 'schreibt {d}',
  terminal: 'führt aus: {d}',
  recherchiert: 'recherchiert {d}',
  delegiert: 'gibt ab: {d}',
  werkzeug: 'benutzt {d}',
  antwortet: 'antwortet …',
  wartet: 'wartet auf einen Hintergrundjob',
}

/** Der Construct-Raum: dieselbe Arbeit wie im Chat, als Raum statt als Text. */
/** Größe eines Elements in Pixeln (ohne Transform), für den Fernseher. */
function useGroesse(ref: React.RefObject<HTMLElement | null>) {
  const [g, setG] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => {
      if (e) setG({ w: e.contentRect.width, h: e.contentRect.height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return g
}

// Wo man die Figur anklicken kann (Prozent): am Podest bzw. an der Werkbank.
const FIGUR_PODEST: Rechteck = { l: FIGUR.x - 4, t: FIGUR.y - FIGUR.h + 3, w: 8, h: FIGUR.h - 3 }
const FIGUR_WERKBANK: Rechteck = { l: 66.8, t: 26.6, w: 9.2, h: 51 }

// Picker der Eingabe (/model, /mode …) → passende Station im Raum.
const PICKER_ANSICHT: Record<PickerName, Ansicht> = {
  folder: 'projekte',
  mode: 'ausruestung',
  model: 'ausruestung',
  effort: 'ausruestung',
}

/** Der Construct-Raum: dieselbe Arbeit wie im Chat, als Raum statt als Text. */
/** Lautsprecher wie ⚙ und ⏻: eine Linie in der Schriftfarbe, kein buntes Emoji. */
function Lautsprecher({ aus }: { aus: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ verticalAlign: 'middle' }}
    >
      <path d="M2.5 6h2.5l3.5-3v10l-3.5-3h-2.5z" />
      {aus ? (
        <path d="M11 6l3.5 4M14.5 6L11 10" />
      ) : (
        <path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.8 3.6a6 6 0 0 1 0 8.8" />
      )}
    </svg>
  )
}

export function RaumView() {
  const { t } = useTranslation()
  const assistant = useSettings((st) => st.boot.assistant)
  const workspace = useSettings((st) => st.boot.workspace)
  const conv = useChat((st) => st.active())
  const folder = useChat((st) => st.folder)
  const mode = useChat((st) => st.mode)
  const providers = useProviders()
  const version = useVersion()
  const setRaum = useUi((st) => st.setRaum)
  const [ansicht, setAnsicht] = useState<Ansicht | null>(null)
  const schliessen = useCallback(() => setAnsicht(null), [])
  // Überfahrene Station: die Kamera stellt darauf scharf. `form` bleibt beim
  // Verlassen stehen, damit die Unschärfe sauber ausblendet.
  const [fokus, setFokus] = useState<StationId | null>(null)
  const [form, setForm] = useState<StationId | null>(null)
  // Durch den Monitor: 'rein' = in die Chat-Ansicht, 'raus' = beim Betreten
  // des Raums kommt man aus dem Monitor heraus. Farbe = Hintergrund der
  // Farbwelt, in die bzw. aus der man taucht.
  const [tauchen, setTauchen] = useState<'rein' | 'raus' | null>('raus')
  const [vorhang, setVorhang] = useState(true)
  const [tauchFarbe] = useState(
    () => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#000',
  )
  useEffect(() => {
    // erst ein Bild ganz nah am Monitor zeichnen, dann herausfahren
    let id = requestAnimationFrame(() => {
      id = requestAnimationFrame(() => setTauchen(null))
    })
    return () => cancelAnimationFrame(id)
  }, [])
  const eintauchen = useCallback(() => {
    setAnsicht(null)
    setFokus(null)
    setTauchen('rein')
  }, [])
  useEffect(() => {
    if (tauchen !== 'rein') return
    const id = setTimeout(() => setRaum(false), 1050)
    return () => clearTimeout(id)
  }, [tauchen, setRaum])
  const welt = useRef<HTMLDivElement>(null)
  /** Ebenen über dem Raumbild werden mit unscharf, außer an ihrer Station. */
  const weichAusser = (id: StationId) => !!fokus && !ansicht && fokus !== id
  const weltGroesse = useGroesse(welt)

  useEffect(() => {
    if (!ansicht) return
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAnsicht(null)
    }
    addEventListener('keydown', esc)
    return () => removeEventListener('keydown', esc)
  }, [ansicht])

  const lage = useMemo(
    () =>
      lageAus(
        conv ? [...conv.history, ...(conv.run?.items ?? [])] : [],
        !!conv?.busy,
        !!conv?.nachlauf,
      ),
    [conv],
  )
  const figurDateien = useSettings((st) => st.boot.figur)
  const figur = useMemo(() => eigeneFigur(figurDateien) ?? CODY, [figurDateien])
  // Arbeitet die Chefin für die Firma (verteilt, prüft), während du nichts fragst,
  // redet sie: sie erklärt. An die Werkbank geht sie dafür nicht.
  const teamStand = useTeamStand().data
  const chefRedet =
    !lage.live && lage.phase === 'ruht' && !!teamStand?.aktiv.some((x) => x.agent === 'chef')
  const pose = useRuhigePose(chefRedet ? 'erklaeren' : POSE_VON[lage.phase])
  const amWerk = pose === 'arbeiten'
  // Team-Modus: das Büro hinten im Raum; null, wenn der Modus aus ist.
  const buero = useBuero(!amWerk)
  const besucht = !!buero?.besuch
  // Arbeitet die Firma und redest du gerade nicht mit dem Assistenten, gehört die
  // Sprechblase dem, der dort spricht (sonst wie immer deine letzte Antwort).
  const team = useTeamBlase(buero?.werk ?? null)
  const teamSpricht = !!team && !lage.live
  const teamAmWerk = teamSpricht && team.slug === buero?.werk
  useRaumKlang({ ansicht, fokus, tauchen, amWerk })
  // Lautsprecher im Kopf: alles an bzw. alles aus (fein in ⚙ → Aussehen).
  const sound = useSettings((st) => st.settings.sound)
  const saveSettings = useSettings((st) => st.save)
  const stumm = !sound.effekte && !sound.musik
  // Das Standbild am Podest verschwindet erst, wenn das Video der Pose wirklich
  // läuft — spielt es nicht (Codec, Autoplay), bleibt die Figur einfach stehen.
  const [videoPose, setVideoPose] = useState<Pose | null>(null)
  const imVideo = VIDEO_AN && !amWerk && !besucht && videoPose === pose
  const videoMeldung = (p: Pose) => (laeuft: boolean) =>
    setVideoPose((v) => (laeuft ? p : v === p ? null : v))
  const status = lage.phase === 'ruht' ? '' : t(PHASE_TEXT[lage.phase], { d: lage.detail })

  // Sprechblase: Klick auf die Figur blendet sie aus und ein. Zugemacht gilt
  // nur für diese Antwort — kommt eine neue, geht sie von selbst wieder auf.
  // Schlüssel = deine wievielte Frage: bleibt stehen, wenn der Lauf endet
  // und die Antwort in den Verlauf wandert.
  const fragen = conv ? conv.history.filter((i) => i.kind === 'user').length : 0
  const blasenLage = teamSpricht ? team.lage : lage
  const blasenStatus = teamSpricht
    ? blasenLage.phase === 'ruht'
      ? ''
      : t(PHASE_TEXT[blasenLage.phase], { d: blasenLage.detail })
    : status
  const antwortKey = teamSpricht ? `team:${team.run}` : `${conv?.key ?? ''}:${fragen}`
  const [zuFuer, setZuFuer] = useState<string | null>(null)
  const blaseZu = zuFuer === antwortKey
  const hatBlase = !!(blasenLage.md || blasenStatus)
  const blaseUmschalten = () => setZuFuer(blaseZu ? null : antwortKey)

  // Schilder der Stationen zeigen, was gerade eingestellt ist.
  const model = conv?.model ?? ''
  const modelName = t(modelInfo(model, providers.data ?? [])?.l ?? 'Modell')
  const modusName = t((MODES.find((m) => m.v === mode) ?? MODES[0]).l.replace(/^\S+\s/, ''))
  // Projekt: das der Session, sonst der Ordner für die nächste neue.
  const projekt = baseName((conv?.sessionId ? conv.cwd : null) ?? folder ?? workspace)
  // Archiv: welche Session gerade offen ist (neue ohne ID: noch ohne Titel).
  const sessions = useSessions()
  const sessionTitel = conv?.sessionId
    ? (sessions.data?.sessions.find((x) => x.id === conv.sessionId)?.title ?? '')
    : ''
  const hinweis = (st: (typeof STATIONEN)[number]) =>
    st.id === 'regal'
      ? projekt || t(st.hint)
      : st.id === 'pult'
        ? `${modelName} · ${modusName}`
        : st.id === 'archiv'
          ? conv?.sessionId
            ? t('Offen: {t}', { t: sessionTitel || t('diese Session') })
            : t('Offen: neue Session')
          : t(st.hint)

  const auftritt = ansicht ? AUFTRITT[ansicht] : null
  // Kompakt (Handy, Tablet hochkant): der Raum ist ein Panorama zum Wischen,
  // die Kamera bleibt beim ganzen Raum, Stationen öffnen als Karte von unten.
  const kompakt = useMedien(KOMPAKT)
  const kamera: Kamera = tauchen ? EINTAUCHEN : kompakt ? GANZ : (auftritt ?? GANZ)
  const flaeche = useRef<HTMLDivElement>(null)
  // Wohin das Panorama schaut: zur offenen Station, sonst zu Cody.
  const blickX = auftritt
    ? auftritt.ziel[0]
    : amWerk || buero?.werk
      ? FIGUR_WERKBANK.l + FIGUR_WERKBANK.w / 2
      : FIGUR.x
  const ersterBlick = useRef(true)
  useEffect(() => {
    const el = flaeche.current
    const buehne = el?.firstElementChild as HTMLElement | null | undefined
    if (!kompakt || !el || !buehne) return
    const zu = (glatt: boolean) =>
      el.scrollTo({
        left: buehne.offsetLeft + (buehne.offsetWidth * blickX) / 100 - el.clientWidth / 2,
        behavior: glatt ? 'smooth' : 'auto',
      })
    zu(!ersterBlick.current)
    ersterBlick.current = false
    // Drehen des Geräts: neu ausrichten (nur bei anderer Breite — die
    // Adressleiste mobiler Browser ändert ständig nur die Höhe).
    let breite = el.clientWidth
    const ro = new ResizeObserver(() => {
      if (el.clientWidth !== breite) zu(false)
      breite = el.clientWidth
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [kompakt, blickX])
  const blase =
    hatBlase && !blaseZu ? (
      <Sprechblase
        key={antwortKey}
        name={teamSpricht && team.slug !== 'chef' ? team.name : assistant}
        farbe={teamSpricht && team.slug !== 'chef' ? team.farbe : undefined}
        status={blasenStatus}
        md={blasenLage.md}
        live={blasenLage.live}
        rechts={teamSpricht ? teamAmWerk : amWerk}
        team={teamAmWerk}
        unten={kompakt}
        onVerlauf={() => {
          if (teamSpricht) {
            // Der ganze Zug steht in den Aufträgen, bei der Person
            const a = useAuftraegeAnsicht.getState()
            a.oeffne(team.auftrag)
            a.sichtWechseln(team.slug)
            setAnsicht('auftraege')
          } else setAnsicht('protokoll')
        }}
        onZu={blaseUmschalten}
      />
    ) : null
  const panel =
    ansicht && auftritt ? (
      <Projektion
        key={ansicht}
        blatt={kompakt}
        auftritt={auftritt}
        titel={t(TITEL[ansicht])}
        hinweis={
          ansicht === 'protokoll'
            ? t('Der ganze Verlauf dieser Session')
            : ansicht === 'einstellungen'
              ? t('Was du siehst und womit du redest')
              : t(STATIONEN.find((st) => st.panel === ansicht)?.hint ?? '')
        }
        onClose={schliessen}
      >
        {ansicht === 'protokoll' ? (
          <div className={s.protokollInhalt} data-scroll>
            <ChatView />
          </div>
        ) : (
          <KartenInhalt panel={ansicht as PanelId} onDone={schliessen} />
        )}
      </Projektion>
    ) : null
  return (
    <div className={`${s.raum} ${ansicht ? s.raumFokus : ''}`}>
      <header className={s.kopf}>
        <span className={s.marke}>
          <b>◢◤</b> CONSTRUCT
          {version.data?.version && <small className={s.version}>{version.data.version}</small>}
        </span>
        <span className={s.kopfRechts}>
          <button
            type="button"
            className={s.knopfRund}
            onClick={() => void saveSettings({ sound: { effekte: stumm, musik: stumm } })}
            title={stumm ? t('Ton an') : t('Ton aus')}
            aria-label={stumm ? t('Ton an') : t('Ton aus')}
            aria-pressed={!stumm}
          >
            <Lautsprecher aus={stumm} />
          </button>
          <button
            type="button"
            className={`${s.knopfRund} ${ansicht === 'einstellungen' ? s.knopfRundAn : ''}`}
            onClick={() => setAnsicht(ansicht === 'einstellungen' ? null : 'einstellungen')}
            title={t('Einstellungen')}
            aria-label={t('Einstellungen')}
          >
            ⚙
          </button>
          <BeendenKnopf className={`${s.knopfRund} ${s.knopfAus}`} />
        </span>
      </header>
      <div className={s.zuKlein}>
        <p>{t('Der Raum braucht einen größeren Bildschirm.')}</p>
        <button type="button" className={s.knopf} onClick={() => setRaum(false)}>
          ▤ {t('Zur Chat-Ansicht')}
        </button>
      </div>
      <div className={s.flaeche} ref={flaeche}>
        <div className={s.buehne}>
          <div className={s.fenster}>
            <div
              ref={welt}
              className={`${s.welt} ${ansicht ? s.weltFokus : ''} ${tauchen === 'rein' ? s.weltRein : ''} ${tauchen === 'raus' ? s.weltSofort : ''}`}
              style={{ transform: weltTransform(kamera) }}
              onClick={() => ansicht && schliessen()}
            >
              <img className={s.bild} src={raumBild} alt="" draggable={false} />
              {/* Monitor und Tastatur gehören fest zur Werkbank. */}
              <img
                className={s.ebene}
                style={platz(WERKBANK)}
                src={geraeteBild}
                alt=""
                draggable={false}
              />
              <img
                className={s.ebene}
                style={platz(KLEMMBRETT)}
                src={klemmbrettBild}
                alt=""
                draggable={false}
              />
              {!SCHEIN && (
                <img
                  className={`${s.unschaerfe} ${fokus && !ansicht ? s.fokusAn : ''}`}
                  style={ohneStation(form)}
                  src={unscharfBild}
                  alt=""
                  draggable={false}
                />
              )}
              <Fernseher welt={weltGroesse} voll={!!tauchen} weich={weichAusser('monitore')} />
              <WandBinaeruhr welt={weltGroesse} weich={weichAusser('uhr')} />
              <WandKontingent welt={weltGroesse} weich={weichAusser('uhr')} />
              <img
                className={`${s.ebene} ${weichAusser('tafel') ? s.kastenWeich : ''}`}
                style={platz(KASTEN)}
                src={kastenBild}
                alt=""
                draggable={false}
              />
              <img
                className={`${s.ebene} ${weichAusser('postfach') ? s.kastenWeich : ''}`}
                style={platz(POSTKORB)}
                src={postkorbBild}
                alt=""
                draggable={false}
              />
              {buero && (
                <>
                  <Buero
                    stand={buero}
                    weich={weichAusser('firma')}
                    onOeffnen={(slug) => {
                      usePersonal.getState().zeigeAkte(slug)
                      setFokus(null)
                      setAnsicht('personal')
                    }}
                    onFokus={(an) => {
                      if (an) {
                        setFokus('firma')
                        setForm('firma')
                      } else setFokus((f) => (f === 'firma' ? null : f))
                    }}
                  />
                  {buero.besuch && (
                    <Besucher
                      besuch={buero.besuch}
                      stand={buero}
                      bild={figur.posen.idle}
                      reden={figur.reden}
                      podest={FIGUR}
                    />
                  )}
                </>
              )}
              <RegalSchild name={projekt} welt={weltGroesse} weich={weichAusser('regal')} />
              <div
                className={`${s.figur} ${lage.live ? s.figurAktiv : ''} ${amWerk || besucht ? s.weg : ''} ${imVideo ? s.still : ''}`}
                role="img"
                aria-label={assistant}
                style={{
                  left: `${FIGUR.x}%`,
                  top: `${FIGUR.y - FIGUR.h}%`,
                  height: `${FIGUR.h}%`,
                }}
              >
                {POSEN.map((p) => (
                  <img
                    key={p}
                    src={figur.posen[p]}
                    alt=""
                    draggable={false}
                    className={p === pose ? s.poseAn : ''}
                  />
                ))}
              </div>
              {VIDEO_AN &&
                POSEN.map((p) => {
                  const clip = figur.videos[p]
                  return (
                    clip && (
                      <PoseVideo
                        key={`${figur.name}-${p}`}
                        clip={clip}
                        ort={PODEST_VIDEO}
                        an={pose === p && !besucht}
                        onLaeuft={videoMeldung(p)}
                      />
                    )
                  )
                })}
              <img
                className={`${s.ebene} ${s.amWerk} ${amWerk ? s.amWerkDa : ''}`}
                style={platz(WERKBANK)}
                src={figur.werkbank}
                alt=""
                draggable={false}
              />
              {VIDEO_AN && figur.videos.arbeiten && (
                <PoseVideo
                  key={`${figur.name}-arbeiten`}
                  clip={figur.videos.arbeiten}
                  ort={WERKBANK}
                  an={amWerk}
                  onLaeuft={videoMeldung('arbeiten')}
                />
              )}
              {SCHEIN ? (
                <Schein id={form} an={!!fokus && !ansicht} />
              ) : (
                <div
                  className={`${s.fokusSchleier} ${fokus && !ansicht ? s.fokusAn : ''}`}
                  style={ohneStation(form)}
                />
              )}
              {STATIONEN.filter((st) => st.id !== 'firma' || buero).map((st) => {
                const an = lage.station === st.id
                const zeigen = () => {
                  setFokus(st.id)
                  setForm(st.id)
                }
                const weg = () => setFokus((f) => (f === st.id ? null : f))
                return (
                  <button
                    key={st.id}
                    type="button"
                    className={`${s.station} ${an ? s.stationAn : ''} ${st.t < 12 ? s.schildUnten : ''} ${st.form ? s.stationForm : ''}`}
                    style={platz(st)}
                    onClick={() => {
                      setFokus(null)
                      if (st.panel === 'chat') eintauchen()
                      else setAnsicht(st.panel)
                    }}
                    onMouseEnter={zeigen}
                    onMouseLeave={weg}
                    onFocus={zeigen}
                    onBlur={weg}
                    aria-label={t(st.label)}
                  >
                    {/* Klickbar nur die echte Form. Sie sitzt auf einem eigenen Element,
                        sonst schneidet sie das Schild mit ab. */}
                    {st.form && (
                      <span
                        className={s.trefferForm}
                        style={{
                          clipPath: `polygon(${st.form.map(([x, y]) => `${x}% ${y}%`).join(', ')})`,
                        }}
                      />
                    )}
                    <span className={s.schild}>
                      <b>{t(st.label)}</b>
                      <span>{an && status ? status : hinweis(st)}</span>
                    </span>
                  </button>
                )
              })}
              <button
                type="button"
                className={s.figurKnopf}
                style={platz(amWerk ? FIGUR_WERKBANK : FIGUR_PODEST)}
                onClick={blaseUmschalten}
                aria-label={blaseZu ? t('Sprechblase zeigen') : t('Sprechblase ausblenden')}
                title={blaseZu ? t('Sprechblase zeigen') : t('Sprechblase ausblenden')}
              />
              {hatBlase && blaseZu && (
                <button
                  type="button"
                  className={`${s.denkpunkte} ${(teamSpricht ? teamAmWerk : amWerk) ? s.denkpunkteWerk : ''} ${blasenLage.live ? s.denkpunkteLive : ''}`}
                  onClick={blaseUmschalten}
                  aria-label={t('Sprechblase zeigen')}
                >
                  <i />
                  <i />
                  <i />
                </button>
              )}
              {!kompakt && blase}
            </div>
            {!kompakt && auftritt?.seite && <Weiss auftritt={auftritt} />}
          </div>
          {!kompakt && panel && auftritt?.seite && (
            <>
              <Leitlinie auftritt={auftritt} />
              {panel}
            </>
          )}
        </div>
      </div>
      {kompakt && !ansicht && blase}
      {kompakt && panel}
      <div className={s.sprechzeile}>
        <Composer raum onPicker={(p) => setAnsicht(PICKER_ANSICHT[p])} />
      </div>
      {(tauchen === 'rein' || vorhang) && (
        <div
          className={`${s.tauchen} ${tauchen === 'rein' ? s.tauchenRein : s.tauchenRaus}`}
          style={{ background: tauchFarbe }}
          onAnimationEnd={() => tauchen !== 'rein' && setVorhang(false)}
        />
      )}
    </div>
  )
}

/** Sparsamer Hover: weicher Schein um das Objekt (nur dessen Fläche). */
function Schein({ id, an }: { id: StationId | null; an: boolean }) {
  const bild = id && bildVon('schein', id)
  if (!id || !bild) return null
  const f = FORM[id]
  return (
    <span
      className={`${s.schein} ${an ? s.fokusAn : ''}`}
      style={{
        left: `${f.l - SCHEIN_RAND.x}%`,
        top: `${f.t - SCHEIN_RAND.y}%`,
        width: `${f.w + 2 * SCHEIN_RAND.x}%`,
        height: `${f.h + 2 * SCHEIN_RAND.y}%`,
        maskImage: `url(${bild})`,
        WebkitMaskImage: `url(${bild})`,
      }}
    />
  )
}

/** Die Seite, auf der der Inhalt erscheint, läuft ins Weiß des Construct aus. */
function Weiss({ auftritt }: { auftritt: Auftritt }) {
  const w = 'rgba(247, 248, 248, 0.97)'
  const b = auftritt.breite
  const richtung = auftritt.seite === 'rechts' ? 'to left' : 'to right'
  return (
    <div
      className={s.weiss}
      style={{
        background: `linear-gradient(${richtung}, ${w} 0%, ${w} ${b + 3}%, rgba(247, 248, 248, 0) ${b + 17}%)`,
      }}
    />
  )
}

/** Feine Linie vom Inhalt zur Station, wie eine Beschriftung in einer Skizze. */
function Leitlinie({ auftritt }: { auftritt: Auftritt }) {
  const [sx, sy] = aufBuehne(auftritt, auftritt.ziel)
  const rechts = auftritt.seite === 'rechts'
  const kante = rechts ? 100 - 3 - auftritt.breite : 3 + auftritt.breite
  const knick = rechts ? kante - 2.5 : kante + 2.5
  const y = 13
  return (
    <>
      <svg
        className={`${s.leitlinie} ${rechts ? '' : s.leitlinieRechts}`}
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden
      >
        <polyline
          points={`${kante},${y} ${knick},${y} ${sx},${sy}`}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <span className={s.leitpunkt} style={{ left: `${sx}%`, top: `${sy}%` }} aria-hidden />
    </>
  )
}

/** Inhalt einer Station: erscheint neben ihr im Weiß, kein Fenster. */
function Projektion({
  auftritt,
  titel,
  hinweis,
  onClose,
  blatt = false,
  children,
}: {
  auftritt: Auftritt
  titel: string
  hinweis: string
  onClose: () => void
  /** Kompakt: als Karte von unten statt neben der Station. */
  blatt?: boolean
  children: ReactNode
}) {
  const { t } = useTranslation()
  const rechts = auftritt.seite === 'rechts'
  return (
    <section
      className={
        blatt ? s.blatt : `${s.projektion} ${rechts ? s.projektionRechts : s.projektionLinks}`
      }
      style={
        blatt ? undefined : { width: `${auftritt.breite}%`, [rechts ? 'right' : 'left']: '3%' }
      }
    >
      <header className={s.projektionKopf}>
        <div>
          <h2>{titel}</h2>
          {hinweis && <p>{hinweis}</p>}
        </div>
        <button type="button" onClick={onClose} aria-label={t('Schließen')} title="Esc">
          ✕
        </button>
      </header>
      <div className={s.projektionInhalt}>{children}</div>
    </section>
  )
}

/** Sprechblase neben der Figur. Wie Untertitel steht darin immer nur ein
 *  Abschnitt der Antwort — beim Sprechen der jüngste, danach lässt sich mit
 *  ‹ › blättern. Alles am Stück steht im Verlauf. Steht die Figur an der
 *  Werkbank, wandert die Blase nach links. */
function Sprechblase({
  name,
  farbe,
  status,
  md,
  live,
  rechts,
  team = false,
  unten = false,
  onVerlauf,
  onZu,
}: {
  name: string
  /** Akzentfarbe "r, g, b" (Mitarbeiter); ohne = die des Raums. */
  farbe?: string
  status: string
  md: string
  live: boolean
  rechts: boolean
  /** Ein Mitarbeiter an der Werkbank spricht (eigener, schmaler Platz). */
  team?: boolean
  /** Kompakt: als Untertitel über der Sprechzeile statt neben der Figur. */
  unten?: boolean
  onVerlauf: () => void
  onZu: () => void
}) {
  const { t } = useTranslation()
  const teile = useMemo(() => abschnitte(md), [md])
  // null = immer der jüngste Abschnitt; eine Zahl = selbst geblättert
  const [wahl, setWahl] = useState<number | null>(null)
  const letzter = Math.max(0, teile.length - 1)
  const nr = Math.min(wahl ?? letzter, letzter)
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (el && live && nr === letzter) el.scrollTop = el.scrollHeight
  }, [md, live, nr, letzter])
  const gehe = (n: number) => setWahl(n >= letzter ? null : Math.max(0, n))
  return (
    <section
      className={`${s.blase} ${unten ? s.blaseUnten : rechts ? s.blaseLinks : ''} ${team ? s.blaseTeam : ''} ${live ? s.blaseLive : ''}`}
      style={farbe ? { ['--accent-rgb' as string]: farbe } : undefined}
      onClick={(e) => e.stopPropagation()}
    >
      <header className={s.blasenKopf}>
        <b>{name}</b>
        {status && <span className={s.status}>{status}</span>}
        <button type="button" className={s.blasenKnopf} onClick={onVerlauf}>
          ☰ {t('Verlauf')}
        </button>
        <button
          type="button"
          className={s.blasenZu}
          onClick={onZu}
          aria-label={t('Sprechblase ausblenden')}
          title={t('Sprechblase ausblenden')}
        >
          ✕
        </button>
      </header>
      {teile.length > 0 && (
        <div ref={ref} className={s.blasenText} data-scroll>
          <Markdown
            key={nr}
            className={s.blasenSeite}
            text={teile[nr] ?? ''}
            streaming={live && nr === letzter}
          />
        </div>
      )}
      {teile.length > 1 && (
        <footer className={s.blasenFuss}>
          <button
            type="button"
            onClick={() => gehe(nr - 1)}
            disabled={nr === 0}
            aria-label={t('Voriger Abschnitt')}
          >
            ‹
          </button>
          {teile.length <= 9 ? (
            <span className={s.punkte}>
              {teile.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  className={i === nr ? s.punktAn : ''}
                  onClick={() => gehe(i)}
                  aria-label={`${i + 1} / ${teile.length}`}
                />
              ))}
            </span>
          ) : (
            <span className={s.seitenzahl}>
              {nr + 1} / {teile.length}
            </span>
          )}
          <button
            type="button"
            onClick={() => gehe(nr + 1)}
            disabled={nr === letzter}
            aria-label={t('Nächster Abschnitt')}
          >
            ›
          </button>
          {wahl !== null && live && (
            <button type="button" className={s.aktuell} onClick={() => setWahl(null)}>
              {t('aktuell')} ›
            </button>
          )}
        </footer>
      )}
    </section>
  )
}
