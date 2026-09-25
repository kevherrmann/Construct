import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Settings } from '@/lib/bootstrap'
import { THEMES } from '@/lib/themes'
import { useSettings } from '@/stores/settings'
import { Section } from './parts'
import { pickUpload, previewStyle } from './helpers'
import s from './Settings.module.css'

// Theme-Wechsel wirkt sofort: save() ruft applyTheme.
export function ThemeSection() {
  const { t } = useTranslation()
  const theme = useSettings((st) => st.settings.theme || 'matrix')
  const save = useSettings((st) => st.save)
  return (
    <Section id="farbwelt">
      <div className={s.thGrid}>
        {THEMES.map((th) => (
          <button
            type="button"
            key={th.key}
            className={`${s.th} ${theme === th.key ? s.on : ''}`}
            onClick={() => void save({ theme: th.key })}
          >
            <span className={s.sw}>
              {th.swatch.map((c, i) => (
                <i key={i} style={{ background: c }} />
              ))}
            </span>
            <span className={s.thName}>
              {t(th.name)}
              {theme === th.key && <b>{t('AKTIV')}</b>}
            </span>
            <span className={s.thDesc}>{t(th.description)}</span>
          </button>
        ))}
      </div>
    </Section>
  )
}

type Bg = Settings['background']

// Drei Zustände: Matrix-Regen (Vorgabe), eigenes Bild, oder schlicht dunkel.
// Abdunkeln ist kein Schmuck, sondern Lesbarkeit: Grün auf einem hellen Foto
// ist unlesbar.
export function BackgroundSection() {
  const { t } = useTranslation()
  const bg = useSettings((st) => st.settings.background)
  const save = useSettings((st) => st.save)
  const mode = bg.mode || 'matrix'
  const [dim, setDim] = useState(bg.dim ?? 60)
  const file = useRef<HTMLInputElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])

  const apply = (patch: Partial<Bg>) => void save({ background: patch })
  // Der Regler speichert erst, wenn er zur Ruhe kommt — sonst schriebe jedes
  // Zwischen-Prozent eine Datei.
  const slide = (v: number) => {
    setDim(v)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => apply({ dim: v }), 300)
  }
  const upload = async (f: File | undefined) => {
    const url = await pickUpload(f, t('Upload fehlgeschlagen'))
    if (url) apply({ image: url, mode: 'image' })
  }

  const modes: { v: Bg['mode']; title: string; d: string }[] = [
    { v: 'matrix', title: t('Matrix-Regen'), d: t('Die Vorgabe. Kostet etwas Rechenleistung.') },
    {
      v: 'image',
      title: t('Eigenes Bild'),
      d: t('Ersetzt den Regen. Wird abgedunkelt, damit die Schrift lesbar bleibt.'),
    },
    { v: 'plain', title: t('Schlicht dunkel'), d: t('Nichts im Hintergrund — am sparsamsten.') },
  ]

  return (
    <Section id="hintergrund">
      {modes.map((m) => (
        <div className={s.row} key={m.v}>
          <label>
            <input
              type="radio"
              name="bgm"
              value={m.v}
              checked={mode === m.v}
              onChange={() => apply({ mode: m.v })}
            />
            <span>
              <span className={s.t}>{m.title}</span>
              <span className={s.d}>{m.d}</span>
            </span>
          </label>
        </div>
      ))}
      <div style={{ marginTop: 12 }}>
        <button type="button" className={s.btn} onClick={() => file.current?.click()}>
          {t('🖼 Bild wählen…')}
        </button>
        <button
          type="button"
          className={s.btn}
          onClick={() => apply({ image: '', mode: 'matrix' })}
        >
          {t('✕ Bild entfernen')}
        </button>
        <div style={{ marginTop: 12 }}>
          <label className={s.d} htmlFor="bgDim">
            {t('Abdunkeln:')} <b>{dim} %</b>
          </label>
          <input
            id="bgDim"
            type="range"
            min={0}
            max={95}
            className={s.slider}
            value={dim}
            onChange={(e) => slide(+e.target.value)}
          />
        </div>
        <div className={s.prev} style={previewStyle(bg, dim)}>
          {bg.image ? (
            <span>{t('VORSCHAU')}</span>
          ) : (
            <span style={{ opacity: 0.5 }}>{t('kein Bild gewählt')}</span>
          )}
        </div>
      </div>
      <input
        ref={file}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          void upload(e.target.files?.[0])
          e.target.value = ''
        }}
      />
    </Section>
  )
}
