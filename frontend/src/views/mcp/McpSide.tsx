import { useTranslation } from 'react-i18next'
import { useMcp } from '@/api/mcp'
import { useSettings } from '@/stores/settings'
import s from './McpSide.module.css'

// Konnektoren aus `claude mcp list`. Einrichten geht nur in der CLI oder auf claude.ai.
export function McpSide() {
  const { t } = useTranslation()
  const assistant = useSettings((st) => st.boot.assistant)
  const { data, isPending } = useMcp()
  const servers = data?.servers ?? []

  let body
  if (isPending) body = <div className={s.hint}>{t('⟲ prüfe Konnektoren…')}</div>
  else if (!servers.length)
    body = (
      <div className={s.hint}>
        {t('keine MCP-Server konfiguriert')}
        {data?.error ? ` (${data.error})` : ''}
      </div>
    )
  else
    body = (
      <>
        {servers.map((m) => (
          <div key={m.name} className={s.sess} title={m.url}>
            <span className={s.t}>
              {m.ok ? '🟢' : m.needs_auth ? '🔑' : '🔴'} {m.name}
            </span>
            <span className={s.d}>{m.status}</span>
          </div>
        ))}
        <div className={`${s.hint} ${s.legend}`}>
          {t('🟢 aktiv · 🔑 braucht Login · 🔴 Problem')}
          <br />
          <br />
          {t('Freischalten: im Terminal')} <code>claudec</code> → <code>/mcp</code>
          {t(', oder auf')} <b>claude.ai → Connectors</b>.
        </div>
      </>
    )

  return (
    <div>
      <div className={s.hint}>
        {t('Konnektoren / MCP-Server — worauf {a} zugreifen kann', { a: assistant })}
      </div>
      {body}
    </div>
  )
}
