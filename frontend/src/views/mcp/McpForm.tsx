import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { MCP_NAME, useMcpHinzufuegen, type McpTransport } from '@/api/mcp'
import s from './McpSide.module.css'

interface Paar {
  k: string
  v: string
}

/** Leere Schlüssel fallen weg; Werte bleiben, wie sie sind (können Tokens sein). */
const zuMap = (p: Paar[]) =>
  Object.fromEntries(p.filter((x) => x.k.trim()).map((x) => [x.k.trim(), x.v]))

// Neuer MCP-Server für Claude Code. Werte von Umgebungsvariablen und Headern
// stehen in Passwortfeldern und verschwinden mit dem Formular: nach dem
// Speichern liegen sie nur noch in der Konfiguration von Claude Code.
// Bereich immer "user": "local" gälte nur für genau den Arbeitsordner, nicht
// für Unterordner. Sessions in ~/projects/construct sähen den Server nicht.
export function McpForm({ onClose }: { onClose: (eingerichtet?: string) => void }) {
  const { t } = useTranslation()
  const id = useId()
  const add = useMcpHinzufuegen()
  const [name, setName] = useState('')
  const [art, setArt] = useState<McpTransport>('stdio')
  const [befehl, setBefehl] = useState('')
  const [argumente, setArgumente] = useState('')
  const [url, setUrl] = useState('')
  const [env, setEnv] = useState<Paar[]>([])
  const [headers, setHeaders] = useState<Paar[]>([])
  const [hinweis, setHinweis] = useState('')
  const form = useRef<HTMLFormElement>(null)

  // Das Formular öffnet unter der Liste, oft unterhalb des sichtbaren Bereichs.
  useEffect(() => form.current?.scrollIntoView({ block: 'nearest' }), [])

  const stdio = art === 'stdio'
  const nameFalsch = name !== '' && !MCP_NAME.test(name)

  const senden = (e: FormEvent) => {
    e.preventDefault()
    if (!MCP_NAME.test(name)) return setHinweis(t('Name: nur Buchstaben, Ziffern, - und _.'))
    if (stdio && !befehl.trim()) return setHinweis(t('Für stdio fehlt der Befehl.'))
    if (!stdio && !url.trim()) return setHinweis(t('Die URL fehlt.'))
    setHinweis('')
    add.mutate(
      stdio
        ? {
            name,
            transport: art,
            scope: 'user',
            command: befehl.trim(),
            args: argumente
              .split('\n')
              .map((a) => a.trim())
              .filter(Boolean),
            env: zuMap(env),
          }
        : { name, transport: art, scope: 'user', url: url.trim(), headers: zuMap(headers) },
      { onSuccess: () => onClose(name) },
    )
  }

  const fehler = hinweis || add.error?.message

  return (
    <form
      ref={form}
      className={s.form}
      onSubmit={senden}
      // Esc schließt nur das Formular, nicht die Raum-Karte drumherum.
      onKeyDown={(e) => {
        if (e.key !== 'Escape') return
        e.stopPropagation()
        if (!add.isPending) onClose()
      }}
      aria-busy={add.isPending}
    >
      <div className={s.formKopf}>{t('Neuer MCP-Server')}</div>

      <div className={s.feld}>
        <label htmlFor={`${id}-n`} className={s.lbl}>
          {t('Name')}
        </label>
        <input
          id={`${id}-n`}
          className={s.in}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('z. B. github')}
          autoFocus
          spellCheck={false}
          autoComplete="off"
          aria-invalid={nameFalsch}
          aria-describedby={`${id}-name`}
        />
        <span id={`${id}-name`} className={nameFalsch ? s.feldErr : s.feldHint}>
          {t('Buchstaben, Ziffern, - und _')}
        </span>
      </div>

      <Wahl
        titel={t('Art')}
        name={`${id}-art`}
        wert={art}
        setze={(v) => {
          // Ein Fehler zur vorigen Art passt nicht mehr.
          setArt(v)
          setHinweis('')
          add.reset()
        }}
        optionen={['stdio', 'http', 'sse']}
      />

      {stdio ? (
        <>
          <label className={s.feld}>
            <span className={s.lbl}>{t('Befehl')}</span>
            <input
              className={`${s.in} ${s.mono}`}
              value={befehl}
              onChange={(e) => setBefehl(e.target.value)}
              placeholder="npx"
              spellCheck={false}
              autoComplete="off"
            />
          </label>
          <label className={s.feld}>
            <span className={s.lbl}>{t('Argumente, eins pro Zeile')}</span>
            <textarea
              className={`${s.in} ${s.mono}`}
              rows={3}
              value={argumente}
              onChange={(e) => setArgumente(e.target.value)}
              placeholder={'-y\n@modelcontextprotocol/server-github'}
              spellCheck={false}
            />
          </label>
          <Paare
            titel={t('Umgebungsvariablen')}
            neu={t('+ Variable')}
            schluessel={t('NAME')}
            paare={env}
            setze={setEnv}
          />
        </>
      ) : (
        <>
          <label className={s.feld}>
            <span className={s.lbl}>{t('URL')}</span>
            <input
              className={`${s.in} ${s.mono}`}
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://"
              spellCheck={false}
              autoComplete="off"
            />
          </label>
          <Paare
            titel={t('Header (optional)')}
            neu={t('+ Header')}
            schluessel={t('Authorization')}
            paare={headers}
            setze={setHeaders}
          />
        </>
      )}

      {fehler && (
        <div className={s.err} role="alert">
          {fehler}
        </div>
      )}

      <div className={s.knoepfe}>
        <button type="submit" className={`${s.btn} ${s.haupt}`} disabled={add.isPending}>
          {add.isPending ? t('richte ein…') : t('Hinzufügen')}
        </button>
        <button type="button" className={s.btn} disabled={add.isPending} onClick={() => onClose()}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

/** Umschalter als Radiogruppe: echte Auswahl, per Pfeiltasten bedienbar. */
function Wahl<T extends string>(p: {
  titel: string
  name: string
  wert: T
  setze: (v: T) => void
  optionen: T[]
}) {
  return (
    <fieldset className={s.wahl}>
      <legend className={s.lbl}>{p.titel}</legend>
      <div className={s.segmente}>
        {p.optionen.map((o) => (
          <label key={o} className={s.segment}>
            <input
              type="radio"
              name={p.name}
              value={o}
              checked={p.wert === o}
              onChange={() => p.setze(o)}
            />
            <span>{o}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function Paare(p: {
  titel: string
  neu: string
  schluessel: string
  paare: Paar[]
  setze: (v: Paar[]) => void
}) {
  const { t } = useTranslation()
  const aendern = (i: number, x: Partial<Paar>) =>
    p.setze(p.paare.map((q, j) => (j === i ? { ...q, ...x } : q)))

  return (
    <fieldset className={s.wahl}>
      <legend className={s.lbl}>{p.titel}</legend>
      {p.paare.map((q, i) => (
        <div key={i} className={s.paar}>
          <input
            className={`${s.in} ${s.mono}`}
            value={q.k}
            onChange={(e) => aendern(i, { k: e.target.value })}
            placeholder={p.schluessel}
            aria-label={t('Name')}
            spellCheck={false}
            autoComplete="off"
          />
          <input
            className={`${s.in} ${s.mono}`}
            type="password"
            value={q.v}
            onChange={(e) => aendern(i, { v: e.target.value })}
            placeholder={t('Wert')}
            aria-label={t('Wert zu {n}', { n: q.k || p.schluessel })}
            // Kein Passwortmanager: das ist kein Login, sondern ein Token.
            autoComplete="new-password"
          />
          <button
            type="button"
            className={s.x}
            aria-label={t('Zeile entfernen')}
            title={t('Zeile entfernen')}
            onClick={() => p.setze(p.paare.filter((_, j) => j !== i))}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        type="button"
        className={s.mehr}
        onClick={() => p.setze([...p.paare, { k: '', v: '' }])}
      >
        {p.neu}
      </button>
    </fieldset>
  )
}
