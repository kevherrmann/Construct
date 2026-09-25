import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  PROV_ICON,
  ollamaCancel,
  ollamaDelete,
  ollamaInstall,
  ollamaPull,
  refreshProviders,
  saveProvider,
  stopBonsai,
  useBonsai,
  useOllama,
  useProviders,
  type Provider,
} from '@/api/providers'
import { fmtGB, pct } from '@/lib/format'
import { rich } from '@/lib/rich'
import { trServer } from '@/lib/serverText'
import { useDialogs } from '@/stores/dialogs'
import { useSettings } from '@/stores/settings'
import { Dialog } from './Dialog'
import s from './ProvidersDialog.module.css'

const errText = (e: unknown) => trServer(e instanceof Error ? e.message : String(e))

// ---------- Ein Anbieter: Key/URL, speichern & testen, abschalten ----------
function ProviderCard({ p }: { p: Provider }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [key, setKey] = useState('')
  const [url, setUrl] = useState(() =>
    p.base_url && p.base_url !== p.default_base ? p.base_url : '',
  )
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])

  const status = p.configured
    ? p.error
      ? '⚠ ' + trServer(p.error)
      : t('✓ aktiv — {n} Modelle', { n: (p.models || []).length })
    : t('— nicht eingerichtet')
  const dot = p.configured ? (p.error ? '#ff5c5c' : 'var(--green)') : '#444'

  const save = async () => {
    setBusy(true)
    setMsg(t('⟲ speichere & teste …'))
    const body: Parameters<typeof saveProvider>[0] = { id: p.id, enabled: true }
    if (p.needs_key && key.trim()) body.api_key = key.trim()
    if (p.id === 'ollama') body.base_url = url.trim()
    try {
      const j = await saveProvider(body)
      setMsg(
        j.ok
          ? t('✅ verbunden — {n} Modelle', { n: j.models })
          : '⚠ ' + trServer(j.error || '?') + ' ' + t('(gespeichert — Standard-Modelle aktiv)'),
      )
      await refreshProviders(qc)
      // Kurz stehen lassen, dann frisch zeichnen wie die alte Oberfläche.
      timer.current = setTimeout(() => {
        setMsg('')
        setKey('')
        setBusy(false)
      }, 1200)
    } catch (e) {
      setBusy(false)
      setMsg('⚠ ' + errText(e))
    }
  }

  const off = async () => {
    await saveProvider({ id: p.id, enabled: false }).catch(() => undefined)
    await refreshProviders(qc)
  }

  return (
    <div className={s.acc}>
      <div className={s.head}>
        <span className={s.dot} style={{ background: dot }} />
        <b>
          {PROV_ICON[p.id] || '🌐'} {trServer(p.label)}
        </b>
        <span className={s.st}>{status}</span>
      </div>
      <div className={s.vhint} style={{ padding: '4px 0 0' }}>
        {trServer(p.hint)}
      </div>
      <div className={s.row}>
        {p.needs_key && (
          <input
            type="password"
            autoComplete="new-password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={
              p.key_set
                ? '••••••••  ' + t('(gespeichert — nur zum Ändern neu eingeben)')
                : 'API-Key'
            }
          />
        )}
        {p.id === 'ollama' && (
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={t('URL (Standard: {u})', { u: p.default_base })}
          />
        )}
        <button type="button" className={s.tbtn} disabled={busy} onClick={save}>
          {p.configured ? t('SPEICHERN & TESTEN') : t('AKTIVIEREN')}
        </button>
        {p.configured && (
          <button
            type="button"
            className={`${s.tbtn} ${s.red}`}
            title={t('Anbieter deaktivieren (Key bleibt gespeichert)')}
            onClick={off}
          >
            {t('✕ AUS')}
          </button>
        )}
        <span className={s.vhint} style={{ flex: 1 }}>
          {msg}
        </span>
      </div>
      {/* Ollama immer — enthält notfalls den Install-Knopf. Bonsai: liegt der
          Server gerade im VRAM? + Knopf zum Freigeben. */}
      {p.id === 'ollama' && <OllamaBox />}
      {p.id === 'bonsai' && <BonsaiBox />}
    </div>
  )
}

// ---------- Bonsai: Server-Zustand (VRAM belegt?) ----------
function BonsaiBox() {
  const { t } = useTranslation()
  const st = useBonsai()
  const [busy, setBusy] = useState(false)
  if (!st.data) return null
  if (!st.data.available)
    return (
      <div className={s.vhint}>
        {rich(
          t(
            '⚠ Bonsai-Demo nicht gefunden — <code>setup.sh</code> im Bonsai-Ordner ausführen oder <code>BONSAI_DIR</code> setzen.',
          ),
        )}
      </div>
    )
  const stop = async () => {
    setBusy(true)
    await stopBonsai().catch(() => undefined)
    await st.refetch()
    setBusy(false)
  }
  return (
    <div className={s.row} style={{ alignItems: 'center' }}>
      <span className={s.vhint} style={{ flex: 1 }}>
        {st.data.running
          ? t('🟢 läuft — Modell im VRAM (stoppt nach {n} Min Leerlauf von selbst)', {
              n: st.data.idle_min,
            })
          : t('⚪ aus — VRAM frei, startet beim ersten Prompt')}
      </span>
      {st.data.running && (
        <button type="button" className={s.tbtn} disabled={busy} onClick={stop}>
          {t('⏹ JETZT STOPPEN')}
        </button>
      )}
    </div>
  )
}

// ---------- Ollama-Modelle verwalten (Liste, Download mit Fortschritt, Löschen) ----------
function OllamaBox() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = useOllama(true)
  const [free, setFree] = useState('')
  const [installing, setInstalling] = useState(false)
  const seen = useRef(new Set<string>())
  const d = q.data

  // Frisch fertig gewordene Downloads bzw. die Installation: Modell-Listen
  // (Dialog und 🧠-Picker) einmalig nachladen.
  useEffect(() => {
    if (!d) return
    const ins = d.install
    if (d.reachable && ins?.done && !ins.error && ins.status && !seen.current.has('__install__')) {
      seen.current.add('__install__')
      void refreshProviders(qc)
    }
    for (const [m, st] of Object.entries(d.pulls ?? {}))
      if (st.done && !st.error && !seen.current.has(m)) {
        seen.current.add(m)
        void refreshProviders(qc)
      }
  }, [d, qc])

  if (!d) return <div className={s.vhint}>{t('⟲ prüfe Ollama …')}</div>

  const pull = async (model: string) => {
    try {
      await ollamaPull(model)
    } catch (e) {
      window.alert(t('Download konnte nicht starten') + ': ' + errText(e))
    }
    void q.refetch()
  }
  const del = async (model: string) => {
    if (
      !window.confirm(
        t('Modell „{m}“ wirklich von der Platte löschen?', { m: model }) +
          '\n\n' +
          t('(Kann jederzeit neu geladen werden.)'),
      )
    )
      return
    try {
      await ollamaDelete(model)
    } catch (e) {
      window.alert(errText(e) || t('Löschen fehlgeschlagen'))
    }
    void refreshProviders(qc)
    void q.refetch()
  }
  const cancel = async (model: string) => {
    await ollamaCancel(model).catch(() => undefined)
    void q.refetch()
  }

  // Ollama läuft (noch) nicht → Installieren/Starten direkt aus dem Dialog.
  if (!d.reachable) {
    const ins = d.install
    if (ins && !ins.done) {
      const p = pct(ins)
      return (
        <div className={s.ollRow}>
          <span className={s.ollName}>⚙ Ollama</span>
          {ins.total > 0 && (
            <span className={s.prog}>
              <i style={{ width: `${p}%` }} />
            </span>
          )}
          <span className={s.meta}>
            {trServer(ins.status || '…')}
            {ins.total ? ` · ${p}% · ${fmtGB(ins.completed)} / ${fmtGB(ins.total)}` : ''}
          </span>
        </div>
      )
    }
    const install = async () => {
      setInstalling(true)
      await ollamaInstall().catch(() => undefined)
      await q.refetch()
      setInstalling(false)
    }
    return (
      <>
        {ins?.error ? (
          <div className={`${s.vhint} ${s.err}`}>⚠ {trServer(ins.error).slice(0, 300)}</div>
        ) : d.error ? (
          <div className={`${s.vhint} ${s.err}`}>{trServer(d.error).slice(0, 200)}</div>
        ) : null}
        <div className={s.row}>
          <button
            type="button"
            className={s.obtn}
            style={{ padding: '9px 16px' }}
            disabled={installing}
            onClick={install}
          >
            {installing
              ? '⟲ …'
              : d.bin
                ? t('▶ OLLAMA STARTEN')
                : t('⬇ OLLAMA INSTALLIEREN & STARTEN')}
          </button>
          <span className={s.vhint} style={{ flex: 1, margin: 0 }}>
            {d.bin
              ? t('Ollama ist installiert, läuft aber gerade nicht — ein Klick startet es.')
              : rich(
                  t(
                    'Cody lädt das offizielle Linux-Paket (~1–2 GB), entpackt es nach <code>~/.cody-ollama</code> und startet es — ganz ohne Terminal. Startet nach einem Neustart automatisch mit.',
                  ),
                )}
          </span>
        </div>
      </>
    )
  }

  const inst = d.installed ?? []
  const pulls = d.pulls ?? {}
  const have = new Set(inst.map((m) => m.name))
  const offer = (d.catalog ?? []).filter((c) => !have.has(c.name) && !pulls[c.name])
  const go = () => {
    if (free.trim()) void pull(free.trim())
  }

  return (
    <>
      {d.error && <div className={`${s.vhint} ${s.err}`}>{trServer(d.error)}</div>}
      <div className={s.uh} style={{ marginTop: 10 }}>
        {t('INSTALLIERTE MODELLE ({n})', { n: inst.length })}
      </div>
      {!inst.length && !d.error && (
        <div className={s.vhint} style={{ padding: '2px 0' }}>
          {t('Noch keine Modelle installiert — unten eins aussuchen und ⬇ klicken.')}
        </div>
      )}
      {inst.map((m) => (
        <div key={m.name} className={s.ollRow}>
          <span className={s.ollName}>🦙 {m.name}</span>
          <span className={s.meta}>
            {fmtGB(m.size)}
            {m.param ? ' · ' + m.param : ''}
            {m.quant ? ' · ' + m.quant : ''}
          </span>
          <button
            type="button"
            className={`${s.obtn} ${s.red}`}
            title={t('Modell von der Platte löschen')}
            onClick={() => void del(m.name)}
          >
            {t('🗑 LÖSCHEN')}
          </button>
        </div>
      ))}
      {Object.entries(pulls).map(([m, st]) => {
        if (st.done && st.error)
          return (
            <div key={m} className={s.ollRow}>
              <span className={s.ollName}>⬇ {m}</span>
              <span className={`${s.meta} ${s.err}`}>⚠ {trServer(st.error).slice(0, 160)}</span>
            </div>
          )
        if (!st.done) {
          const p = pct(st)
          return (
            <div key={m} className={s.ollRow}>
              <span className={s.ollName}>⬇ {m}</span>
              <span className={s.prog}>
                <i style={{ width: `${p}%` }} />
              </span>
              <span className={s.meta}>
                {st.total
                  ? `${p}% · ${fmtGB(st.completed)} / ${fmtGB(st.total)}`
                  : st.status || '…'}
              </span>
              <button
                type="button"
                className={`${s.obtn} ${s.red}`}
                title={t('Download abbrechen')}
                onClick={() => void cancel(m)}
              >
                ✕
              </button>
            </div>
          )
        }
        return (
          <div key={m} className={s.ollRow}>
            <span className={s.ollName}>✅ {m}</span>
            <span className={s.meta}>{t('fertig geladen — steht im 🧠-Menü bereit')}</span>
          </div>
        )
      })}
      {offer.length > 0 && (
        <>
          <div className={s.uh} style={{ marginTop: 12 }}>
            {t('BELIEBTE MODELLE ZUM LADEN')}
          </div>
          {offer.map((c) => (
            <div key={c.name} className={s.ollRow}>
              <span className={s.ollName}>{c.name}</span>
              <span className={s.meta}>{trServer(c.desc)}</span>
              <button type="button" className={s.obtn} onClick={() => void pull(c.name)}>
                ⬇ {c.size}
              </button>
            </div>
          ))}
        </>
      )}
      <div className={s.row}>
        <input
          value={free}
          onChange={(e) => setFree(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              go()
            }
          }}
          placeholder={t('anderes Modell von ollama.com/library — z.B. qwen3:32b')}
          autoComplete="off"
        />
        <button type="button" className={s.obtn} style={{ padding: '8px 14px' }} onClick={go}>
          {t('⬇ LADEN')}
        </button>
      </div>
    </>
  )
}

// ---------- Der Dialog ----------
function ProvidersBody() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const assistant = useSettings((st) => st.boot.assistant)
  const q = useProviders()
  // Beim Öffnen frisch vom Server — der Stand im Cache kann alt sein.
  useEffect(() => {
    void qc.invalidateQueries({ queryKey: ['llm-providers'] })
  }, [qc])

  return (
    <>
      <p style={{ opacity: 0.85 }}>
        {rich(
          t(
            'Neben Claude Code kannst du hier weitere Anbieter hinterlegen — ChatGPT, Gemini, DeepSeek, lokale Ollama-Modelle oder jede andere OpenAI-kompatible API. Sie laufen über <b>Hermes</b> und können damit ebenfalls Dateien und Terminal. Auswahl danach unten links über 🧠.',
          ),
        )}
      </p>
      {!q.data ? (
        <div className={s.vhint} style={{ padding: 8 }}>
          {t('⟲ lade Anbieter …')}
        </div>
      ) : (
        <>
          {q.data.map((p) => (
            <ProviderCard key={p.id} p={p} />
          ))}
          <div className={s.vhint} style={{ marginTop: 10 }}>
            {rich(
              t(
                '🔒 Keys liegen nur auf deinem Server in <code>.llm-config.json</code> (chmod 600) — sie tauchen nie im Browser auf.',
              ),
            )}
            <br />
            {rich(
              t(
                '⚡ Fremde Modelle laufen über <b>Hermes</b> und können damit Dateien und Terminal. Skills, Kalender und E-Mail bleiben Claude Code vorbehalten. Beim Modellwechsel mitten im Gespräch nimmt {a} den bisherigen Verlauf automatisch mit.',
                { a: assistant },
              ),
            )}
          </div>
        </>
      )}
    </>
  )
}

export function ProvidersDialog() {
  const { t } = useTranslation()
  const open = useDialogs((d) => d.current === 'providers')
  const close = useDialogs((d) => d.close)
  return (
    <Dialog open={open} onClose={close} title={t('🧠 KI-ANBIETER')} wide>
      <ProvidersBody />
    </Dialog>
  )
}
