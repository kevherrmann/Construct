import { useEffect, useMemo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useFolders, useProviders } from '@/api/chat'
import { CLAUDE_MODELS, MODES, extModels, modelInfo, provIcon } from '@/lib/chat/models'
import { baseName } from '@/lib/format'
import { useChat } from '@/stores/chat'
import { useDialogs } from '@/stores/dialogs'
import { useSettings } from '@/stores/settings'
import s from './Pickers.module.css'

export type PickerName = 'folder' | 'mode' | 'model'

interface PickerProps {
  name: PickerName
  open: PickerName | null
  setOpen: (p: PickerName | null) => void
  bar: ReactNode
  title?: string
  wide?: boolean
  /** Ohne Claude Code wirken Ordner und Modus nicht — abgeblendet zeigen. */
  dim?: boolean
  children: ReactNode
}

function Picker({ name, open, setOpen, bar, title, wide, dim, children }: PickerProps) {
  return (
    <div className={`${s.picker} ${dim ? s.dim : ''}`}>
      {open === name && (
        <div className={`${s.list} ${wide ? s.wide : ''}`} onClick={(e) => e.stopPropagation()}>
          {children}
        </div>
      )}
      <button
        type="button"
        className={s.bar}
        title={title}
        onClick={(e) => {
          e.stopPropagation()
          setOpen(open === name ? null : name)
        }}
      >
        {bar} <span>▾</span>
      </button>
    </div>
  )
}

function Item({
  sel,
  onClick,
  children,
}: {
  sel?: boolean
  onClick?: () => void
  children: ReactNode
}) {
  return (
    <button type="button" className={`${s.item} ${sel ? s.sel : ''}`} onClick={onClick}>
      {children}
    </button>
  )
}

export function Pickers({
  open,
  setOpen,
}: {
  open: PickerName | null
  setOpen: (p: PickerName | null) => void
}) {
  const { t } = useTranslation()
  const hasClaude = useSettings((st) => st.boot.claude)
  const workspace = useSettings((st) => st.boot.workspace)
  const folders = useFolders()
  const providers = useProviders()
  const provs = useMemo(() => providers.data ?? [], [providers.data])
  const { folder, mode, setFolder, setMode, setModel } = useChat()
  const model = useChat((st) => st.active()?.model ?? '')

  // Klick irgendwo sonst schließt das offene Menü.
  useEffect(() => {
    if (!open) return
    const close = () => setOpen(null)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [open, setOpen])

  // Erster Ordner der Liste = der echte Arbeitsordner des Servers. Kein fest
  // verdrahteter Pfad: unter Windows und nativ ist das ein ganz anderer.
  useEffect(() => {
    if (folder == null && folders.data?.[0]) setFolder(folders.data[0])
  }, [folder, folders.data, setFolder])

  // Ohne Claude Code wäre ein Claude-Modell eine Sackgasse: die erste Nachricht
  // liefe in "claude nicht gefunden". Sobald ein externer Anbieter
  // eingerichtet ist, von selbst dorthin schalten.
  useEffect(() => {
    if (hasClaude || model.includes(':')) return
    const e = extModels(provs)[0]
    if (e) setModel(e.v)
  }, [hasClaude, model, provs, setModel])

  const pick = (fn: () => void) => () => {
    fn()
    setOpen(null)
  }
  const claudeHint = hasClaude
    ? ''
    : t(
        ' — wirkt nur mit Claude Code. Die Chat-Modelle (ChatGPT, Gemini …) haben keinen Zugriff auf Dateien.',
      )
  const curMode = MODES.find((m) => m.v === mode) ?? MODES[0]
  const curModel = modelInfo(model, provs) ?? CLAUDE_MODELS[0]!
  const shownFolder = folder ?? workspace

  return (
    <div className={s.bars}>
      <Picker
        name="folder"
        dim={!hasClaude}
        open={open}
        setOpen={setOpen}
        title={t('Arbeitsordner') + claudeHint}
        bar={
          <>
            📂{' '}
            <span className={s.name} title={shownFolder}>
              {baseName(shownFolder)}
            </span>
          </>
        }
      >
        {(folders.data ?? []).map((p) => (
          <Item key={p} sel={p === folder} onClick={pick(() => setFolder(p))}>
            <span title={p}>📂 {baseName(p)}</span>
          </Item>
        ))}
      </Picker>
      <Picker
        name="mode"
        dim={!hasClaude}
        open={open}
        setOpen={setOpen}
        title={t('Berechtigungs-Modus') + claudeHint}
        bar={
          <>
            <span>{curMode.l.split(' ')[0]}</span>{' '}
            <span className={s.name}>{t(curMode.l.split(' ').slice(1).join(' '))}</span>
          </>
        }
      >
        {MODES.map((m) => (
          <Item key={m.v} sel={m.v === mode} onClick={pick(() => setMode(m.v))}>
            {m.l.split(' ')[0]} {t(m.l.split(' ').slice(1).join(' '))}{' '}
            <span className={s.muted}>— {t(m.d)}</span>
          </Item>
        ))}
      </Picker>
      <Picker
        name="model"
        open={open}
        setOpen={setOpen}
        wide
        bar={
          <>
            🧠{' '}
            <span>
              {curModel.prov ? `${provIcon(curModel.prov)} ` : ''}
              {t(curModel.l)}
            </span>
          </>
        }
      >
        <div className={s.head}>
          {t('CLAUDE · VOLLER ZUGRIFF (TOOLS, DATEIEN)')}
          {hasClaude ? '' : t(' — NICHT INSTALLIERT')}
        </div>
        {CLAUDE_MODELS.map((m) => (
          <Item key={m.v} sel={m.v === curModel.v} onClick={pick(() => setModel(m.v))}>
            🧠 {t(m.l)} <span className={s.muted}>— {t(m.d)}</span>
          </Item>
        ))}
        {provs
          .filter((p) => p.configured)
          .map((p) => (
            <div key={p.id}>
              <div className={s.head}>
                {provIcon(p.id)} {p.label.toUpperCase()} · {t('ÜBER HERMES')}
              </div>
              {!p.models?.length && (
                <Item>
                  <span className={s.muted}>
                    {p.error ? `⚠ ${p.error}` : t('(keine Modelle gefunden)')}
                  </span>
                </Item>
              )}
              {(p.models ?? []).map((mid) => {
                const cap = p.tools?.[mid]
                const v = `${p.id}:${mid}`
                return (
                  <Item key={v} sel={v === curModel.v} onClick={pick(() => setModel(v))}>
                    {provIcon(p.id)} {mid}
                    {cap === true ? ' ⚡' : cap == null ? ' ⚡?' : ''}{' '}
                    <span className={s.muted}>
                      — {p.label}
                      {cap === true
                        ? t(' · mit Werkzeugen')
                        : cap == null
                          ? t(' · Werkzeuge unbestätigt')
                          : ''}
                    </span>
                  </Item>
                )
              })}
            </div>
          ))}
        <div className={s.head} />
        <Item onClick={pick(() => useDialogs.getState().open('providers'))}>
          ⚙ <b>{t('KI-Anbieter einrichten…')}</b>{' '}
          <span className={s.muted}>— ChatGPT, Gemini, DeepSeek, Ollama</span>
        </Item>
      </Picker>
    </div>
  )
}
