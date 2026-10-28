import { useMemo, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useUi } from '@/stores/ui'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useSessions, type SessionInfo } from '@/api/chat'
import { apiPost } from '@/lib/api'
import { provIcon } from '@/lib/chat/models'
import { baseName } from '@/lib/format'
import { locale } from '@/lib/i18n'
import { useChat } from '@/stores/chat'
import { useSettings } from '@/stores/settings'
import s from './SessionsSide.module.css'

export function SessionsSide() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const lang = useSettings((st) => st.boot.lang)
  const sessions = useSessions()
  const { newSession, openSession, forgetSession } = useChat(
    useShallow((st) => ({
      newSession: st.newSession,
      openSession: st.openSession,
      forgetSession: st.forgetSession,
    })),
  )
  // Nur, welche Sessions hier gerade arbeiten, als String: die Unterhaltungen
  // selbst ändern sich beim Streamen bei jedem Bild, die Liste müsste mitzeichnen.
  const busyKey = useChat((st) =>
    Object.values(st.convs)
      .filter((c) => c.busy && c.sessionId)
      .map((c) => c.sessionId)
      .join(' '),
  )
  const busyHier = useMemo(() => new Set(busyKey.split(' ').filter(Boolean)), [busyKey])
  const activeSid = useChat((st) => st.active()?.sessionId)
  // Suche und Filter überleben den Wechsel in andere Ansichten.
  const { sessQuery: query, closedFolders: closed, showArchived, showAgents, setSess } = useUi()
  const setSideOpen = useUi((st) => st.setSideOpen)

  const list = sessions.data?.sessions ?? []
  const running = sessions.data?.running ?? {}
  const reload = () => void qc.invalidateQueries({ queryKey: ['sessions'] })
  const q = query.trim().toLowerCase()

  const archCount = list.filter((x) => x.archived).length
  // Sitzungen der Firma: jeder Agentenzug in FACTORIA legt eine eigene an, und
  // die erschlagen die eigenen Gespräche rein zahlenmäßig. Standardmäßig aus;
  // der Schalter erscheint nur, wenn es überhaupt welche gibt.
  const agentCount = list.filter((x) => x.agent).length
  let visible = list.filter((x) => showArchived || !x.archived)
  if (!showAgents) visible = visible.filter((x) => !x.agent)
  if (q) visible = visible.filter((x) => `${x.title} ${x.cwd}`.toLowerCase().includes(q))
  const groups = new Map<string, SessionInfo[]>()
  for (const x of visible) {
    const k = x.cwd || t('(unbekannt)')
    groups.set(k, [...(groups.get(k) ?? []), x])
  }
  const folders = [...groups.keys()].sort(
    (a, b) => groups.get(b)![0]!.mtime - groups.get(a)![0]!.mtime,
  )

  // Mehrere auf einmal löschen oder archivieren: das Kästchen vor jeder
  // Session. Ist etwas angehakt, öffnet ein Klick auf die Zeile die Session
  // nicht mehr, sondern hakt sie an; Shift hakt den Bereich seit dem letzten
  // Klick an. Laufende Sessions bleiben außen vor: ihre Datei schreibt claude
  // gerade noch.
  const [auswahl, setAuswahl] = useState<Set<string>>(new Set())
  const waehlen = auswahl.size > 0
  const [anker, setAnker] = useState<string | null>(null)
  const laeuft = (x: SessionInfo) => !!running[x.id] || busyHier.has(x.id)
  const sichtbar = folders.flatMap((f) => (q || !closed[f] ? groups.get(f)! : []))
  const gewaehlt = list.filter((x) => auswahl.has(x.id))
  const auswahlEnde = () => {
    setAuswahl(new Set())
    setAnker(null)
  }
  const haken = (x: SessionInfo, bereich: boolean) => {
    if (laeuft(x)) return
    const neu = new Set(auswahl)
    const an = !neu.has(x.id)
    const ia = anker ? sichtbar.findIndex((y) => y.id === anker) : -1
    const ib = sichtbar.findIndex((y) => y.id === x.id)
    const ziel =
      bereich && ia >= 0 && ib >= 0 ? sichtbar.slice(Math.min(ia, ib), Math.max(ia, ib) + 1) : [x]
    for (const y of ziel) {
      if (laeuft(y)) continue
      if (an) neu.add(y.id)
      else neu.delete(y.id)
    }
    setAuswahl(neu)
    setAnker(x.id)
  }
  const ordnerHaken = (items: SessionInfo[]) => {
    const frei = items.filter((x) => !laeuft(x))
    const alle = frei.length > 0 && frei.every((x) => auswahl.has(x.id))
    const neu = new Set(auswahl)
    for (const x of frei) {
      if (alle) neu.delete(x.id)
      else neu.add(x.id)
    }
    setAuswahl(neu)
  }
  const alleSichtbaren = () => {
    const frei = sichtbar.filter((x) => !laeuft(x))
    const alle = frei.length > 0 && frei.every((x) => auswahl.has(x.id))
    setAuswahl(alle ? new Set() : new Set(frei.map((x) => x.id)))
  }
  const auswahlArchivieren = async () => {
    // Sind alle schon im Archiv, holt der Knopf sie zurück.
    const archived = !gewaehlt.every((x) => x.archived)
    await Promise.all(
      gewaehlt.map((x) =>
        apiPost(`/api/sessions/${encodeURIComponent(x.id)}/archive`, { archived }).catch(() => {}),
      ),
    )
    auswahlEnde()
    reload()
  }
  const auswahlLoeschen = async () => {
    if (
      !gewaehlt.length ||
      !confirm(
        t('{n} Sessions endgültig löschen?\n\nDas kann nicht rückgängig gemacht werden.', {
          n: gewaehlt.length,
        }),
      )
    )
      return
    for (const x of gewaehlt) {
      await fetch(`/api/sessions/${encodeURIComponent(x.project)}/${encodeURIComponent(x.id)}`, {
        method: 'DELETE',
      }).catch(() => {})
      forgetSession(x.id)
    }
    auswahlEnde()
    reload()
  }

  const open = (x: SessionInfo) => {
    setSideOpen(false)
    navigate('/chat')
    void openSession(x, running[x.id])
  }
  const rename = async (x: SessionInfo) => {
    const name = prompt(
      t('Name für diese Session (leer = automatischer Titel):'),
      x.renamed ? x.title : '',
    )
    if (name === null) return
    await apiPost(`/api/sessions/${encodeURIComponent(x.id)}/rename`, { name }).catch(() => {})
    reload()
  }
  const archive = async (x: SessionInfo) => {
    await apiPost(`/api/sessions/${encodeURIComponent(x.id)}/archive`, {
      archived: !x.archived,
    }).catch(() => {})
    reload()
  }
  const remove = async (x: SessionInfo) => {
    if (
      !confirm(
        t('Session endgültig löschen?\n\n„{title}"\n\nDas kann nicht rückgängig gemacht werden.', {
          title: x.title || x.id,
        }),
      )
    )
      return
    await fetch(`/api/sessions/${encodeURIComponent(x.project)}/${encodeURIComponent(x.id)}`, {
      method: 'DELETE',
    }).catch(() => {})
    forgetSession(x.id)
    reload()
  }

  return (
    <>
      <button
        type="button"
        className={s.newBtn}
        onClick={() => {
          newSession()
          setSideOpen(false)
          navigate('/chat')
        }}
      >
        {t('＋ NEUE SESSION')}
      </button>
      <input
        className={s.search}
        placeholder={t('🔎 Sessions durchsuchen…')}
        autoComplete="off"
        value={query}
        onChange={(e) => setSess({ sessQuery: e.target.value })}
      />
      <div
        className={`${s.toggle} ${showArchived ? s.toggleOn : ''}`}
        onClick={() => setSess({ showArchived: !showArchived })}
      >
        🗄 {t('Archiv')} ({archCount}) ·{' '}
        <span>{showArchived ? t('ausblenden') : t('anzeigen')}</span>
      </div>
      {waehlen && (
        <div className={s.auswahl}>
          <span className={s.anzahl}>{t('{n} ausgewählt', { n: gewaehlt.length })}</span>
          <button type="button" className={s.ab} onClick={alleSichtbaren}>
            {t('alle')}
          </button>
          <button
            type="button"
            className={s.ab}
            disabled={!gewaehlt.length}
            onClick={() => void auswahlArchivieren()}
          >
            {gewaehlt.length && gewaehlt.every((x) => x.archived)
              ? `⤴ ${t('aus Archiv holen')}`
              : `🗄 ${t('archivieren')}`}
          </button>
          <button
            type="button"
            className={`${s.ab} ${s.del}`}
            disabled={!gewaehlt.length}
            onClick={() => void auswahlLoeschen()}
          >
            🗑 {t('löschen')}
          </button>
          <button type="button" className={s.ab} onClick={auswahlEnde}>
            ✕ {t('aufheben')}
          </button>
          <div className={s.tipp}>{t('Shift+Klick wählt einen Bereich.')}</div>
        </div>
      )}
      {agentCount > 0 && (
        <div
          className={`${s.toggle} ${showAgents ? s.toggleOn : ''}`}
          onClick={() => setSess({ showAgents: !showAgents })}
        >
          🏢 {t('Firma')} ({agentCount}) ·{' '}
          <span>{showAgents ? t('ausblenden') : t('anzeigen')}</span>
        </div>
      )}
      {!folders.length && sessions.data && (
        <div className={s.hint}>
          {q
            ? t('Nichts gefunden.')
            : showArchived
              ? t('Keine Sessions.')
              : t('Keine aktiven Sessions.')}
        </div>
      )}
      {folders.map((folder) => {
        const items = groups.get(folder)!
        const isOpen = q ? true : !closed[folder] // bei Suche alles aufklappen
        return (
          <div key={folder}>
            <div
              className={s.folder}
              onClick={() => setSess({ closedFolders: { ...closed, [folder]: isOpen } })}
            >
              <span className={s.fa}>{isOpen ? '▾' : '▸'}</span>
              <span className={s.fn} title={folder}>
                ▣ {baseName(folder)}
              </span>
              {waehlen && (
                <Kaestchen
                  an={
                    items.some((x) => !laeuft(x)) &&
                    items.every((x) => laeuft(x) || auswahl.has(x.id))
                  }
                  title={t('ganzen Ordner auswählen')}
                  onClick={() => ordnerHaken(items)}
                />
              )}
              <span className={s.fc}>{items.length}</span>
            </div>
            {isOpen &&
              items.map((x) => {
                const isRunning = busyHier.has(x.id) || !!running[x.id]
                const dt =
                  new Date(x.mtime * 1000).toLocaleString(locale(lang), {
                    day: '2-digit',
                    month: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                  }) + (x.provider ? ` · ${provIcon(x.provider)} ${x.model || x.provider}` : '')
                return (
                  <div
                    key={x.id}
                    title={x.cwd}
                    className={[
                      s.sess,
                      x.id === activeSid ? s.active : '',
                      isRunning ? s.running : '',
                      x.archived ? s.archived : '',
                      waehlen ? s.waehlbar : '',
                    ].join(' ')}
                  >
                    <Kaestchen
                      an={auswahl.has(x.id)}
                      aus={isRunning}
                      title={isRunning ? t('läuft gerade') : t('auswählen')}
                      onClick={(bereich) => haken(x, bereich)}
                    />
                    <div
                      className={s.main}
                      onClick={(e) => (waehlen ? haken(x, e.shiftKey) : open(x))}
                    >
                      <span className={s.t}>
                        {isRunning ? '⚡ ' : ''}
                        {x.archived ? '🗄 ' : ''}
                        {x.agent ? '🏢 ' : ''}
                        {x.renamed ? '✏ ' : ''}
                        {x.title}
                      </span>
                      <span className={s.d}>{dt}</span>
                    </div>
                    <div className={s.acts} hidden={waehlen}>
                      <button
                        type="button"
                        className={s.sx}
                        title={t('umbenennen')}
                        onClick={() => void rename(x)}
                      >
                        ✏
                      </button>
                      <button
                        type="button"
                        className={s.sx}
                        title={x.archived ? t('aus Archiv holen') : t('archivieren')}
                        onClick={() => void archive(x)}
                      >
                        {x.archived ? '⤴' : '🗄'}
                      </button>
                      <button
                        type="button"
                        className={`${s.sx} ${s.del}`}
                        title={t('löschen')}
                        onClick={() => void remove(x)}
                      >
                        🗑
                      </button>
                    </div>
                  </div>
                )
              })}
          </div>
        )
      })}
    </>
  )
}

/** Eigenes Kästchen statt <input type="checkbox">: das native ist im dunklen
 *  Design kaum zu sehen. */
function Kaestchen(props: {
  an: boolean
  aus?: boolean
  title: string
  onClick: (bereich: boolean) => void
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={props.an}
      disabled={props.aus}
      title={props.title}
      className={`${s.box} ${props.an ? s.boxAn : ''}`}
      // Shift+Klick soll anhaken, nicht Text markieren
      onMouseDown={(e) => e.shiftKey && e.preventDefault()}
      onClick={(e) => {
        e.stopPropagation()
        props.onClick(e.shiftKey)
      }}
    >
      {props.an ? '✓' : ''}
    </button>
  )
}
