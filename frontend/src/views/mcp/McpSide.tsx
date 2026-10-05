import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MCP_NAME, useMcp, useMcpEntfernen, type McpServer } from '@/api/mcp'
import { McpForm } from './McpForm'
import s from './McpSide.module.css'

// Konnektoren aus `claude mcp list`. Eigene Server richtet man hier ein und
// entfernt sie wieder (über `claude mcp add-json` / `remove`); Konnektoren von
// claude.ai bleiben claude.ai → Connectors vorbehalten.
export function McpSide() {
  const { t } = useTranslation()
  const { data, isPending, isFetching } = useMcp()
  const [offen, setOffen] = useState(false)
  const [fertig, setFertig] = useState('')
  const neuKnopf = useRef<HTMLButtonElement>(null)
  const zurueck = useRef(false)
  useEffect(() => {
    if (!offen && zurueck.current) neuKnopf.current?.focus()
    zurueck.current = false
  }, [offen])
  const servers = data?.servers ?? []

  let body
  // Bei jedem Öffnen läuft `claude mcp list` neu (bis zu 30 s) — solange
  // das dauert, nicht so tun, als wäre die alte Liste aktuell.
  if (isPending || isFetching) body = <div className={s.hint}>{t('⟲ prüfe Konnektoren…')}</div>
  else if (!servers.length)
    // Leer: die Form des Eintrags, der hier hinkommt, statt eines Symbols.
    body = (
      <>
        <div className={s.leer} aria-hidden="true">
          <i className={s.leerPunkt} />
          <i className={s.leerBalken} />
          <i className={s.leerBalken2} />
        </div>
        <div className={s.hint}>
          {t('Noch kein MCP-Server eingerichtet.')}
          {data?.error ? ` (${data.error})` : ''}
        </div>
      </>
    )
  else
    body = (
      <>
        <ul className={s.liste}>
          {servers.map((m) => (
            <Eintrag key={m.name} m={m} />
          ))}
        </ul>
        <div className={`${s.hint} ${s.legend}`}>
          {t('🟢 aktiv · 🔑 braucht Login · 🔴 Problem')}
          <br />
          <br />
          {t('Freischalten: im Terminal')} <code>claudec</code> → <code>/mcp</code>
          {t(', oder auf')} <b>claude.ai → Connectors</b>.
          {servers.some((m) => !MCP_NAME.test(m.name)) && (
            <>
              <br />
              <br />
              {t(
                'Ohne ✕: Konnektoren von claude.ai und Plugin-Server lassen sich hier nicht entfernen.',
              )}
            </>
          )}
        </div>
      </>
    )

  return (
    <div>
      <div className={s.hint}>
        {t('MCP-Server für Claude Code. Hermes nutzt diese Liste nicht.')}
      </div>
      {body}
      {offen ? (
        <McpForm
          onClose={(name) => {
            zurueck.current = true
            setOffen(false)
            setFertig(name ?? '')
          }}
        />
      ) : (
        <>
          {fertig && (
            <div className={s.ok} role="status">
              {t('„{n}“ eingerichtet.', { n: fertig })}
            </div>
          )}
          <button
            ref={neuKnopf}
            type="button"
            className={s.neu}
            onClick={() => {
              setFertig('')
              setOffen(true)
            }}
          >
            {t('+ Server hinzufügen')}
          </button>
        </>
      )}
    </div>
  )
}

function Eintrag({ m }: { m: McpServer }) {
  const { t } = useTranslation()
  const weg = useMcpEntfernen(m.name)
  const [frage, setFrage] = useState(false)
  const xKnopf = useRef<HTMLButtonElement>(null)
  const zurueck = useRef(false)
  // Nach Abbrechen steht der Fokus wieder auf dem ✕, nicht irgendwo im Dokument.
  useEffect(() => {
    if (!frage && zurueck.current) xKnopf.current?.focus()
    zurueck.current = false
  }, [frage])
  const abbrechen = () => {
    if (weg.isPending) return
    zurueck.current = true
    setFrage(false)
  }
  // claude.ai-Konnektoren und Plugin-Server verwaltet die CLI nicht.
  const entfernbar = MCP_NAME.test(m.name)

  return (
    <li className={s.sess} title={m.url}>
      <div className={s.zeile}>
        <span className={s.text}>
          <span className={s.t}>
            {m.ok ? '🟢' : m.needs_auth ? '🔑' : '🔴'} {m.name}
          </span>
          <span className={s.d}>{m.status}</span>
        </span>
        {entfernbar && !frage && (
          <button
            ref={xKnopf}
            type="button"
            className={s.x}
            aria-label={t('{n} entfernen', { n: m.name })}
            title={t('{n} entfernen', { n: m.name })}
            onClick={() => {
              weg.reset()
              setFrage(true)
            }}
          >
            ✕
          </button>
        )}
      </div>
      {frage && (
        <div
          className={s.frage}
          // Esc schließt nur die Rückfrage, nicht die Raum-Karte drumherum.
          onKeyDown={(e) => {
            if (e.key !== 'Escape') return
            e.stopPropagation()
            abbrechen()
          }}
        >
          <span>{t('„{n}“ aus Claude Code entfernen?', { n: m.name })}</span>
          <span className={s.knoepfe}>
            <button
              type="button"
              className={`${s.btn} ${s.gefahr}`}
              disabled={weg.isPending}
              // Fokus direkt auf die Rückfrage, damit Tastatur und Vorleser sie finden.
              autoFocus
              onClick={() => weg.mutate()}
            >
              {weg.isPending ? t('entferne…') : t('Entfernen')}
            </button>
            <button type="button" className={s.btn} disabled={weg.isPending} onClick={abbrechen}>
              {t('Abbrechen')}
            </button>
          </span>
          {weg.error && (
            <div className={s.err} role="alert">
              {weg.error.message}
            </div>
          )}
        </div>
      )}
    </li>
  )
}
