import { useState } from 'react'
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
  const { newSession, openSession, forgetSession } = useChat()
  const convs = useChat((st) => st.convs)
  const activeSid = useChat((st) => st.active()?.sessionId)
  const [query, setQuery] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [showAgents, setShowAgents] = useState(false)
  const [closed, setClosed] = useState<Record<string, boolean>>({})

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

  const open = (x: SessionInfo) => {
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
        onChange={(e) => setQuery(e.target.value)}
      />
      <div
        className={`${s.toggle} ${showArchived ? s.toggleOn : ''}`}
        onClick={() => setShowArchived((v) => !v)}
      >
        🗄 {t('Archiv')} ({archCount}) ·{' '}
        <span>{showArchived ? t('ausblenden') : t('anzeigen')}</span>
      </div>
      {agentCount > 0 && (
        <div
          className={`${s.toggle} ${showAgents ? s.toggleOn : ''}`}
          onClick={() => setShowAgents((v) => !v)}
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
              onClick={() => setClosed((c) => ({ ...c, [folder]: isOpen }))}
            >
              <span className={s.fa}>{isOpen ? '▾' : '▸'}</span>
              <span className={s.fn} title={folder}>
                ▣ {baseName(folder)}
              </span>
              <span className={s.fc}>{items.length}</span>
            </div>
            {isOpen &&
              items.map((x) => {
                const conv = Object.values(convs).find((c) => c.sessionId === x.id)
                const isRunning = !!conv?.busy || !!running[x.id]
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
                    ].join(' ')}
                  >
                    <div className={s.main} onClick={() => open(x)}>
                      <span className={s.t}>
                        {isRunning ? '⚡ ' : ''}
                        {x.archived ? '🗄 ' : ''}
                        {x.agent ? '🏢 ' : ''}
                        {x.renamed ? '✏ ' : ''}
                        {x.title}
                      </span>
                      <span className={s.d}>{dt}</span>
                    </div>
                    <div className={s.acts}>
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
