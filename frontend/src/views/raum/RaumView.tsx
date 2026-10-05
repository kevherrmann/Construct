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
import { ChatView } from '@/views/chat/ChatView'
import raumBild from './assets/raum.webp'
import codyIdle from './assets/cody-idle.webp'
import codyDenken from './assets/cody-denken.webp'
import codyLesen from './assets/cody-lesen.webp'
import codyErklaeren from './assets/cody-erklaeren.webp'
import codyWerkbank from './assets/cody-werkbank.webp'
import codyGeraete from './assets/cody-werkbank-geraete.webp'
import codyUnscharf from './assets/cody-raum-unscharf.webp'
import klemmbrettBild from './assets/klemmbrett.webp'
import { abschnitte, lageAus, type Phase } from './lage'
import { KartenInhalt } from './RaumKarten'
import { useRaumKlang } from './useRaumKlang'
import { Fernseher } from './Fernseher'
import { RegalSchild, WandKontingent, Wanduhr } from './Raumdetails'
import { aufBuehne, GANZ, weltTransform, type Kamera } from './kamera'
import {
  AUFTRITT,
  EINTAUCHEN,
  FIGUR,
  KLEMMBRETT,
  PODEST_VIDEO,
  SCHEIN_RAND,
  STATIONEN,
  FORM,
  WERKBANK,
  type Ansicht,
  type Auftritt,
  type PanelId,
  type Rechteck,
  type StationId,
} from './stationen'
import s from './Raum.module.css'

/** 'arbeiten' ist keine Pose am Podest: dafür geht die Figur an die Werkbank
 *  und tippt dort an der Tastatur (statt in die Luft). */
type Pose = 'idle' | 'denken' | 'lesen' | 'arbeiten' | 'erklaeren'
type PodestPose = Exclude<Pose, 'arbeiten'>
const POSEN: PodestPose[] = ['idle', 'denken', 'lesen', 'erklaeren']

/** Kurze Schleife einer Pose. Erstes und letztes Bild = Standbild der Pose,
 *  die Maske (Figur mit Rand) lässt drumherum den Raum durch. */
interface Clip {
  webm: string
  mp4: string
  maske: string
}

interface Figur {
  /** 'cody' oder 'eigen' (static/figur dieser Installation). */
  name: string
  posen: Record<PodestPose, string>
  /** Figur an der Werkbank (Ausschnitt WERKBANK) und Monitor + Tastatur dort. */
  werkbank: string
  geraete: string
  /** Raum unscharf (mit Monitor + Tastatur dieser Figur), für den Hover-Fokus. */
  unscharf: string
  /** Schleifen je Pose: am Podest im Ausschnitt PODEST_VIDEO, 'arbeiten' an
   *  der Werkbank im Ausschnitt WERKBANK. Fehlt eine, bleibt das Standbild. */
  videos: Partial<Record<Pose, Clip>>
  /** Werkbank-Form für Unschärfe und Schein (mit dem Monitor dieser Figur). */
  form?: string
  schein?: string
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
  geraete: codyGeraete,
  unscharf: codyUnscharf,
  videos: videosVon((d) => VIDEO_DATEI[`./assets/video/cody-${d}`]),
}

/** Eigene Figur einer Installation statt Cody: liegt in static/figur
 *  (gitignored), der Server gibt die Dateiliste beim Start mit. Gleiche
 *  Leinwand wie Cody. Pflicht: idle, denken, lesen, erklaeren, werkbank,
 *  werkbank-geraete, raum-unscharf (.webp). Freiwillig: form-werkbank.webp,
 *  schein-werkbank.webp, video/<pose>.webm|mp4 + video/<pose>-maske.webp.
 *  Fehlt etwas Pflicht, bleibt es bei Cody. */
function eigeneFigur(dateien: string[]): Figur | null {
  const da = new Set(dateien)
  const url = (d: string) => (da.has(d) ? `/static/figur/${d}` : undefined)
  const bild = (n: string) => url(`${n}.webp`)
  const [idle, denken, lesen, erklaeren, werkbank, geraete, unscharf] = [
    'idle',
    'denken',
    'lesen',
    'erklaeren',
    'werkbank',
    'werkbank-geraete',
    'raum-unscharf',
  ].map(bild)
  if (!idle || !denken || !lesen || !erklaeren || !werkbank || !geraete || !unscharf) return null
  return {
    name: 'eigen',
    posen: { idle, denken, lesen, erklaeren },
    werkbank,
    geraete,
    unscharf,
    videos: videosVon((d) => url(`video/${d}`)),
    form: bild('form-werkbank'),
    schein: bild('schein-werkbank'),
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

/** Bild aus form/ bzw. schein/. Die Werkbank hängt an der Figur (ihr
 *  Monitor): eigene Figur, sonst `<id>-cody.webp`; alles andere `<id>.webp`. */
function bildVon(ordner: 'form' | 'schein', id: StationId, figur: Figur) {
  const alle = ordner === 'form' ? FORM_BILD : SCHEIN_BILD
  const eigenes = id === 'werkbank' ? figur[ordner] : undefined
  return (
    eigenes ?? alle[`./assets/${ordner}/${id}-cody.webp`] ?? alle[`./assets/${ordner}/${id}.webp`]
  )
}

/** Maske „alles außer dieser Station“ für Unschärfe und Schleier. */
function ohneStation(id: StationId | null, figur: Figur): React.CSSProperties {
  const bild = id && bildVon('form', id, figur)
  if (!id || !bild) return {}
  const f = FORM[id]
  // background-position in %: Versatz = (Fläche − Bild) · p
  const px = f.w >= 100 ? 0 : (f.l / (100 - f.w)) * 100
  const py = f.h >= 100 ? 0 : (f.t / (100 - f.h)) * 100
  const m = {
    image: `url(${bild}), linear-gradient(#000 0 0)`,
    size: `${f.w}% ${f.h}%, 100% 100%`,
    position: `${px}% ${py}%, 0 0`,
  }
  return {
    maskImage: m.image,
    maskSize: m.size,
    maskPosition: m.position,
    maskRepeat: 'no-repeat',
    maskComposite: 'exclude',
    WebkitMaskImage: m.image,
    WebkitMaskSize: m.size,
    WebkitMaskPosition: m.position,
    WebkitMaskRepeat: 'no-repeat',
    WebkitMaskComposite: 'xor',
  }
}

const platz = (r: Rechteck) => ({
  left: `${r.l}%`,
  top: `${r.t}%`,
  width: `${r.w}%`,
  height: `${r.h}%`,
})

/** Schleife einer Pose. Startet beim Einblenden vorn, damit das erste Bild
 *  genau auf dem Standbild liegt — die Überblendung springt dann nicht. */
function PoseVideo({
  clip,
  ort,
  an,
  onLaeuft,
}: {
  clip: Clip
  ort: Rechteck
  an: boolean
  onLaeuft: (v: boolean) => void
}) {
  const ref = useRef<HTMLVideoElement>(null)
  const [laeuft, setLaeuft] = useState(false)
  useEffect(() => {
    const v = ref.current
    if (!v) return
    if (an) {
      v.currentTime = 0
      v.play().catch(() => {}) // Autoplay verweigert: dann bleibt das Standbild
    } else {
      const id = setTimeout(() => v.pause(), 500) // erst nach der Ausblendung
      return () => clearTimeout(id)
    }
  }, [an])
  const melde = (v: boolean) => {
    setLaeuft(v)
    onLaeuft(v)
  }
  return (
    <video
      ref={ref}
      className={`${s.video} ${an && laeuft ? s.videoAn : ''}`}
      style={{
        ...platz(ort),
        maskImage: `url(${clip.maske})`,
        WebkitMaskImage: `url(${clip.maske})`,
      }}
      muted
      loop
      playsInline
      preload="auto"
      aria-hidden
      onPlaying={() => melde(true)}
      onPause={() => melde(false)}
      onError={() => melde(false)}
    >
      <source src={clip.webm} type="video/webm" />
      <source src={clip.mp4} type="video/mp4" />
    </video>
  )
}
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
const FIGUR_WERKBANK: Rechteck = { l: 62.5, t: 28.5, w: 8.5, h: 46 }

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
  const pose = useRuhigePose(POSE_VON[lage.phase])
  const amWerk = pose === 'arbeiten'
  useRaumKlang({ ansicht, fokus, tauchen, amWerk })
  // Lautsprecher im Kopf: alles an bzw. alles aus (fein in ⚙ → Aussehen).
  const sound = useSettings((st) => st.settings.sound)
  const saveSettings = useSettings((st) => st.save)
  const stumm = !sound.effekte && !sound.musik
  // Das Standbild am Podest verschwindet erst, wenn das Video der Pose wirklich
  // läuft — spielt es nicht (Codec, Autoplay), bleibt die Figur einfach stehen.
  const [videoPose, setVideoPose] = useState<Pose | null>(null)
  const imVideo = VIDEO_AN && !amWerk && videoPose === pose
  const videoMeldung = (p: Pose) => (laeuft: boolean) =>
    setVideoPose((v) => (laeuft ? p : v === p ? null : v))
  const status = lage.phase === 'ruht' ? '' : t(PHASE_TEXT[lage.phase], { d: lage.detail })

  // Sprechblase: Klick auf die Figur blendet sie aus und ein. Zugemacht gilt
  // nur für diese Antwort — kommt eine neue, geht sie von selbst wieder auf.
  // Schlüssel = deine wievielte Frage: bleibt stehen, wenn der Lauf endet
  // und die Antwort in den Verlauf wandert.
  const fragen = conv ? conv.history.filter((i) => i.kind === 'user').length : 0
  const antwortKey = `${conv?.key ?? ''}:${fragen}`
  const [zuFuer, setZuFuer] = useState<string | null>(null)
  const blaseZu = zuFuer === antwortKey
  const hatBlase = !!(lage.md || status)
  const blaseUmschalten = () => setZuFuer(blaseZu ? null : antwortKey)

  // Schilder der Stationen zeigen, was gerade eingestellt ist.
  const model = conv?.model ?? ''
  const modelName = t(modelInfo(model, providers.data ?? [])?.l ?? 'Modell')
  const modusName = t((MODES.find((m) => m.v === mode) ?? MODES[0]).l.replace(/^\S+\s/, ''))
  // Projekt: das der Session, sonst der Ordner für die nächste neue.
  const projekt = baseName((conv?.sessionId ? conv.cwd : null) ?? folder ?? workspace)
  const hinweis = (st: (typeof STATIONEN)[number]) =>
    st.id === 'regal'
      ? projekt || t(st.hint)
      : st.id === 'pult'
        ? `${modelName} · ${modusName}`
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
    : amWerk
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
                src={figur.geraete}
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
                  style={ohneStation(form, figur)}
                  src={figur.unscharf}
                  alt=""
                  draggable={false}
                />
              )}
              <Fernseher welt={weltGroesse} voll={!!tauchen} weich={weichAusser('monitore')} />
              <Wanduhr weich={weichAusser('uhr')} />
              <WandKontingent welt={weltGroesse} weich={weichAusser('uhr')} />
              <RegalSchild name={projekt} welt={weltGroesse} weich={weichAusser('regal')} />
              <div
                className={`${s.figur} ${lage.live ? s.figurAktiv : ''} ${amWerk ? s.weg : ''} ${imVideo ? s.still : ''}`}
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
                        an={pose === p}
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
                <Schein id={form} an={!!fokus && !ansicht} figur={figur} />
              ) : (
                <div
                  className={`${s.fokusSchleier} ${fokus && !ansicht ? s.fokusAn : ''}`}
                  style={ohneStation(form, figur)}
                />
              )}
              {STATIONEN.map((st) => {
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
                    className={`${s.station} ${an ? s.stationAn : ''} ${st.t < 12 ? s.schildUnten : ''}`}
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
                  className={`${s.denkpunkte} ${amWerk ? s.denkpunkteWerk : ''} ${lage.live ? s.denkpunkteLive : ''}`}
                  onClick={blaseUmschalten}
                  aria-label={t('Sprechblase zeigen')}
                >
                  <i />
                  <i />
                  <i />
                </button>
              )}
              {hatBlase && !blaseZu && (
                <Sprechblase
                  key={antwortKey}
                  name={assistant}
                  status={status}
                  md={lage.md}
                  live={lage.live}
                  rechts={amWerk}
                  onVerlauf={() => setAnsicht('protokoll')}
                  onZu={blaseUmschalten}
                />
              )}
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
function Schein({ id, an, figur }: { id: StationId | null; an: boolean; figur: Figur }) {
  const bild = id && bildVon('schein', id, figur)
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
  status,
  md,
  live,
  rechts,
  onVerlauf,
  onZu,
}: {
  name: string
  status: string
  md: string
  live: boolean
  rechts: boolean
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
      className={`${s.blase} ${rechts ? s.blaseLinks : ''} ${live ? s.blaseLive : ''}`}
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
