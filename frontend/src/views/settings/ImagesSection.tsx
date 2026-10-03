import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { saveImagesKey, useImagesStatus } from '@/api/settings'
import { rich } from '@/lib/rich'
import { trServer } from '@/lib/serverText'
import { useSettings } from '@/stores/settings'
import { Note, Section } from './parts'
import s from './Settings.module.css'

// Bilder erzeugen über fal.ai: Cody ruft bild.py auf, das Bild erscheint im
// Chat. Der Key geht an den Server (.llm-config.json) und kommt nie zurück.
export function ImagesSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const st = useImagesStatus()
  const model = useSettings((x) => x.settings.images.model)
  const save = useSettings((x) => x.save)
  const [key, setKey] = useState('')
  const [note, setNote] = useState('')

  const configured = !!st.data?.configured
  const store = async (value: string) => {
    setNote('…')
    try {
      const res = await saveImagesKey(value)
      qc.setQueryData(['images'], res)
      setKey('')
      setNote(res.configured ? t('✓ Key gespeichert') : t('✓ Key entfernt'))
    } catch (e) {
      setNote('⚠ ' + trServer((e as Error).message))
    }
  }

  return (
    <Section id="bilder">
      <div className={s.d} style={{ marginBottom: 10 }}>
        {rich(
          t(
            'Bitte {a} um ein Bild, und es erscheint direkt im Chat. Läuft über <b>fal.ai</b> (Guthaben aufladen, kein Abo); den Key gibt es unter fal.ai/dashboard/keys.',
            { a: useSettings.getState().boot.assistant },
          ),
        )}
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('fal.ai-Key')}</span>
          <span className={s.d}>
            {st.data
              ? configured
                ? t('✓ hinterlegt — ein neuer Key ersetzt ihn.')
                : t('Noch kein Key hinterlegt.')
              : '…'}
          </span>
          <span className={s.actionsFlex} style={{ marginTop: 8 }}>
            <input
              className={s.in}
              type="password"
              autoComplete="off"
              spellCheck={false}
              style={{ width: '100%', maxWidth: 420 }}
              value={key}
              placeholder={configured ? '••••••••' : 'fal-…'}
              onChange={(e) => setKey(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && key.trim() && void store(key)}
            />
            <button
              type="button"
              className={s.btn}
              disabled={!key.trim()}
              onClick={() => void store(key)}
            >
              {t('Speichern')}
            </button>
            {configured && (
              <button type="button" className={s.btn} onClick={() => void store('')}>
                {t('Entfernen')}
              </button>
            )}
            <Note text={note} />
          </span>
        </span>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Modell')}</span>
          <span className={s.d}>
            {rich(
              t(
                '<b>GPT Image 2</b> hält sich am genauesten an die Beschreibung, auch bei Schrift und Händen.',
              ),
            )}
          </span>
          <span className={s.actions}>
            <select
              className={s.btn}
              value={model}
              onChange={(e) => void save({ images: { model: e.target.value } })}
            >
              {(st.data?.models ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} · {m.price} {t('pro Bild')}
                </option>
              ))}
            </select>
          </span>
        </span>
      </div>
    </Section>
  )
}
