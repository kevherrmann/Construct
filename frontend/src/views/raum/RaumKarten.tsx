import { Suspense, lazy, useEffect, useMemo, useRef, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { useEvents } from '@/api/calendar'
import { useFolderTree, useFolders } from '@/api/chat'
import { useProviders } from '@/api/providers'
import { FolderNav } from '@/components/chat/FolderNav'
import { rememberFolder } from '@/lib/chat/folders'
import { CLAUDE_MODELS, EFFORTS, MODES, extModels } from '@/lib/chat/models'
import { baseName } from '@/lib/format'
import { locale } from '@/lib/i18n'
import { useSettings } from '@/stores/settings'
import { parseYMD, todayYMD, upcoming } from '@/views/calendar/dates'
import { useChat } from '@/stores/chat'
import { CalendarMain } from '@/views/calendar/CalendarMain'
import { CalendarSide } from '@/views/calendar/CalendarSide'
import { SessionsSide } from '@/views/chat/SessionsSide'
import { MailMain } from '@/views/mail/MailMain'
import { MailSide } from '@/views/mail/MailSide'
import { McpSide } from '@/views/mcp/McpSide'
import { SkillsMain } from '@/views/skills/SkillsMain'
import { SkillsSide } from '@/views/skills/SkillsSide'
import { useSekunde } from '@/hooks/useSekunde'
import { gruppiert, toolBlocks, useItems, useWerkstattDaten } from './daten'
import type { PanelId } from './stationen'
import s from './Raum.module.css'
import { BinaerUhr } from './BinaerUhr'

// Inhalte der Glaskarten. Wo es den Baustein schon gibt (Sessions, Kalender,
// Mail, Skills, MCP), steht hier genau der — dieselbe Funktion wie im Chat.
// Terminal, Werkbank und Ausrüstung sind Raum-eigene Übersichten aus dem
// Gesprächszustand.

// Einstellungen erst beim Öffnen laden, wie in der Chat-Ansicht.
const TicketsMain = lazy(() =>
  import('@/views/tickets/TicketsMain').then((m) => ({ default: m.TicketsMain })),
)
const TicketsSide = lazy(() =>
  import('@/views/tickets/TicketsSide').then((m) => ({ default: m.TicketsSide })),
)
const SettingsMain = lazy(() =>
  import('@/views/settings/SettingsMain').then((m) => ({ default: m.SettingsMain })),
)
const SettingsSide = lazy(() =>
  import('@/views/settings/SettingsSide').then((m) => ({ default: m.SettingsSide })),
)

/** Zwei Spalten wie in der Chat-Ansicht: Liste links, Inhalt rechts. */
function Zweispaltig({ links, rechts }: { links: ReactNode; rechts: ReactNode }) {
  return (
    <div className={s.zweispaltig}>
      <div className={s.spalteLinks}>{links}</div>
      <div className={s.spalteRechts} data-scroll>
        {rechts}
      </div>
    </div>
  )
}

function Sessions({ onDone }: { onDone: () => void }) {
  // Wird eine Session geöffnet oder neu begonnen, hat die Karte ihren Zweck erfüllt.
  const key = useChat((st) => st.activeKey)
  const erster = useRef(key)
  useEffect(() => {
    if (key !== erster.current) onDone()
  }, [key, onDone])
  return (
    <div className={s.einspaltig}>
      <SessionsSide />
    </div>
  )
}

function Projekte({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation()
  const tree = useFolderTree()
  const folders = useFolders()
  const { folder, setFolder } = useChat()
  const pick = (p: string) => {
    rememberFolder(p)
    setFolder(p)
    onDone()
  }
  return (
    <div className={s.einspaltig}>
      <p className={s.hinweis}>
        {t('Der Ordner gilt für die nächste neue Session — eine laufende behält ihren.')}
      </p>
      {tree.data ? (
        <FolderNav tree={tree.data} current={folder} onPick={pick} onClose={onDone} />
      ) : (
        (folders.data ?? []).map((p) => (
          <button key={p} type="button" className={s.zeile} onClick={() => pick(p)}>
            📂 {baseName(p)}
          </button>
        ))
      )}
    </div>
  )
}

const GIT_STATUS: Record<string, [string, string]> = {
  M: ['✎', 'geändert'],
  A: ['✚', 'neu'],
  '??': ['✚', 'neu, noch nicht in git'],
  D: ['✕', 'gelöscht'],
  R: ['↻', 'umbenannt'],
}

function DateiZeile({
  pfad,
  icon,
  titel,
  rel,
}: {
  pfad: string
  icon: string
  titel: string
  rel?: string
}) {
  return (
    <a
      className={s.zeile}
      href={`/api/file?path=${encodeURIComponent(pfad)}`}
      target="_blank"
      rel="noopener"
      title={`${titel} · ${pfad}`}
    >
      <span className={s.zeileIcon}>{icon}</span>
      <b>{baseName(pfad)}</b>
      <span className={s.zeilePfad}>{rel ?? pfad}</span>
    </a>
  )
}

/** Werkbank: was in dieser Session geschrieben wurde und was im Projekt
 *  offen ist (git) — dort taucht auch auf, was per Befehl geändert wurde. */
function Werkbank() {
  const { t } = useTranslation()
  const items = useItems()
  const werkstatt = useWerkstattDaten()
  const dateien = useMemo(() => {
    const m = new Map<string, boolean>()
    for (const d of werkstatt?.dateien ?? []) m.set(d.path, d.neu)
    // Laufendes, das das Protokoll noch nicht hat (und Modelle ohne Protokoll)
    for (const b of toolBlocks(items)) {
      const inp = (b.input ?? {}) as { file_path?: string; path?: string }
      const p = inp.file_path ?? inp.path
      if (
        typeof p === 'string' &&
        /^(Write|Edit|MultiEdit|NotebookEdit|write_file|patch)\b/.test(b.name)
      )
        if (!m.has(p)) m.set(p, /^(Write|write_file)/.test(b.name))
    }
    return [...m.entries()].reverse()
  }, [items, werkstatt])
  const git = werkstatt?.git
  const relativ = (p: string) =>
    git?.root && p.startsWith(git.root + '/') ? p.slice(git.root.length + 1) : p
  return (
    <div className={s.einspaltig}>
      <h3 className={s.abschnitt}>{t('In dieser Session geschrieben')}</h3>
      {dateien.length ? (
        dateien.map(([p, neu]) => (
          <DateiZeile key={p} pfad={p} icon={neu ? '✚' : '✎'} titel={t(neu ? 'neu' : 'geändert')} />
        ))
      ) : (
        <p className={s.hinweis}>
          {t('Noch nichts — Dateien, die per Befehl geändert wurden, stehen unten.')}
        </p>
      )}
      {git?.repo && (
        <>
          <h3 className={s.abschnitt}>
            {t('Offen im Projekt')} <span>git · {git.dateien.length}</span>
          </h3>
          {git.dateien.length ? (
            gruppiert(git.dateien).map((e) =>
              e.art === 'datei' ? (
                <DateiZeile
                  key={e.d.path}
                  pfad={e.d.path}
                  icon={(GIT_STATUS[e.d.status] ?? GIT_STATUS.M!)[0]}
                  titel={t((GIT_STATUS[e.d.status] ?? GIT_STATUS.M!)[1])}
                  rel={relativ(e.d.path)}
                />
              ) : (
                <div key={e.ordner} className={`${s.zeile} ${s.zeileOrdner}`} title={e.ordner}>
                  <span className={s.zeileIcon}>▤</span>
                  <b>{baseName(e.ordner)}/</b>
                  <span className={s.zeilePfad}>
                    {t('{n} Dateien', { n: e.n })} · {relativ(e.ordner)}
                  </span>
                </div>
              ),
            )
          ) : (
            <p className={s.hinweis}>{t('Alles committet.')}</p>
          )}
        </>
      )}
    </div>
  )
}

interface Wahl {
  readonly v: string
  readonly l: string
  readonly d: string
}

function Gruppe({
  titel,
  liste,
  wert,
  setzen,
}: {
  titel: string
  liste: readonly Wahl[]
  wert: string
  setzen: (v: string) => void
}) {
  const { t } = useTranslation()
  return (
    <div className={s.gruppe}>
      <h3>{t(titel)}</h3>
      <div className={s.kacheln}>
        {liste.map((x) => (
          <button
            key={x.v || 'std'}
            type="button"
            className={`${s.kachel} ${x.v === wert ? s.kachelAn : ''}`}
            onClick={() => setzen(x.v)}
          >
            <b>{t(x.l)}</b>
            <span>{t(x.d)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function Ausruestung() {
  const providers = useProviders()
  const { mode, effort, setMode, setModel, setEffort } = useChat()
  const model = useChat((st) => st.active()?.model ?? '')
  const ext = extModels(providers.data ?? [])
  return (
    <div className={s.einspaltig}>
      <Gruppe titel="Modell" liste={[...CLAUDE_MODELS, ...ext]} wert={model} setzen={setModel} />
      <Gruppe titel="Modus" liste={MODES} wert={mode} setzen={setMode} />
      <Gruppe titel="Aufwand" liste={EFFORTS} wert={effort} setzen={setEffort} />
    </div>
  )
}

function Skills() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  return (
    <Zweispaltig
      links={<SkillsSide />}
      rechts={
        params.get('path') ? (
          <SkillsMain />
        ) : (
          <p className={s.hinweis}>{t('Links einen Skill wählen.')}</p>
        )
      }
    />
  )
}

/** ISO-Kalenderwoche */
function kw(d: Date) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7))
  return Math.ceil(((+t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7)
}

const zwei = (n: number) => String(n).padStart(2, '0')

/** Die Wanduhr aus der Nähe: Digitaluhr mit dem Tag als Zeitleiste und dem,
 *  was als Nächstes kommt. */
function DigitalUhr() {
  const { t } = useTranslation()
  const lang = useSettings((st) => st.boot.lang)
  const { data } = useEvents()
  const jetzt = useSekunde()
  const heute = todayYMD()
  const minuten = jetzt.getHours() * 60 + jetzt.getMinutes()
  const naechster = upcoming(data ?? [], heute, 30).find(
    ({ e, d }) => d > heute || !e.time || +e.time.slice(0, 2) * 60 + +e.time.slice(3, 5) >= minuten,
  )
  let bis = ''
  if (naechster?.e.time) {
    const ziel = parseYMD(naechster.d)
    ziel.setHours(+naechster.e.time.slice(0, 2), +naechster.e.time.slice(3, 5))
    const min = Math.max(0, Math.round((+ziel - +jetzt) / 60000))
    bis =
      min < 60
        ? t('in {m} Min.', { m: min })
        : min < 24 * 60
          ? t('in {h} Std. {m} Min.', { h: Math.floor(min / 60), m: min % 60 })
          : t('in {d} Tagen', { d: Math.round(min / 1440) })
  }
  const tag = jetzt.toLocaleDateString(locale(lang), {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
  return (
    <div className={s.digitaluhr}>
      <div className={s.ziffern} aria-live="off">
        <span>{zwei(jetzt.getHours())}</span>
        <i className={jetzt.getSeconds() % 2 ? s.doppelpunktAus : ''}>:</i>
        <span>{zwei(jetzt.getMinutes())}</span>
        <small>{zwei(jetzt.getSeconds())}</small>
      </div>
      <div className={s.datum}>
        {tag} · {t('KW')} {kw(jetzt)}
      </div>
      <BinaerUhr jetzt={jetzt} />
      {naechster ? (
        <div className={s.naechster}>
          <span>{t('Als Nächstes')}</span>
          <b>
            {naechster.e.time ? `${naechster.e.time} · ` : ''}
            {naechster.e.title}
          </b>
          <em>
            {naechster.d === heute
              ? bis || t('heute')
              : `${parseYMD(naechster.d).toLocaleDateString(locale(lang), {
                  weekday: 'short',
                  day: 'numeric',
                  month: 'short',
                })}${bis ? ` · ${bis}` : ''}`}
          </em>
        </div>
      ) : (
        <div className={s.naechster}>
          <span>{t('Als Nächstes')}</span>
          <b>{t('Keine anstehenden Termine.')}</b>
        </div>
      )}
    </div>
  )
}

export function KartenInhalt({ panel, onDone }: { panel: PanelId; onDone: () => void }) {
  switch (panel) {
    case 'sessions':
      return <Sessions onDone={onDone} />
    case 'projekte':
      return <Projekte onDone={onDone} />
    case 'werkbank':
      return <Werkbank />
    case 'ausruestung':
      return <Ausruestung />
    case 'uhr':
      return <DigitalUhr />
    case 'kalender':
      return <Zweispaltig links={<CalendarSide />} rechts={<CalendarMain />} />
    case 'mail':
      return <Zweispaltig links={<MailSide />} rechts={<MailMain />} />
    case 'tickets':
      return (
        <Suspense fallback={null}>
          <Zweispaltig links={<TicketsSide />} rechts={<TicketsMain onDone={onDone} />} />
        </Suspense>
      )
    case 'skills':
      return <Skills />
    case 'mcp':
      return (
        <div className={s.einspaltig}>
          <McpSide />
        </div>
      )
    case 'einstellungen':
      return (
        <Suspense fallback={null}>
          <Zweispaltig links={<SettingsSide ohneHinweis />} rechts={<SettingsMain />} />
        </Suspense>
      )
  }
}
