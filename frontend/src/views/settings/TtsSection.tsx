import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTtsVoices, type Voice } from '@/api/settings'
import { say, stopSay } from '@/lib/audio'
import { rich } from '@/lib/rich'
import { trServer } from '@/lib/serverText'
import { openDialog } from '@/stores/dialogs'
import { useSettings } from '@/stores/settings'
import { Note, Section } from './parts'
import s from './Settings.module.css'

const MODELS = [
  { v: 'gemini-3.8-flash-lite-tts', l: 'Gemini 3.8 Flash-Lite TTS' },
  { v: 'gemini-3.8-flash-tts', l: 'Gemini 3.8 Flash TTS' },
]

const voiceLabel = (v: Voice) =>
  v.name +
  [v.gender, v.pitch, v.accent]
    .filter(Boolean)
    .map((x) => ' · ' + x)
    .join('')

// Stimme und Sprechweise gelten je Oberflächensprache (config.py).
export function TtsSection() {
  const { t } = useTranslation()
  const boot = useSettings((st) => st.boot)
  const tts = useSettings((st) => st.settings.tts)
  const save = useSettings((st) => st.save)
  const lang = boot.lang
  const en = lang === 'en'
  const voices = useTtsVoices(en ? 'en-US' : 'de-DE')
  const curVoice = tts.voice?.[lang] ?? ''
  const [style, setStyle] = useState(tts.style?.[lang] ?? '')
  const [note, setNote] = useState('')

  const list = voices.data?.voices ?? []
  const info = voices.isError
    ? '⚠ ' + trServer(voices.error.message)
    : voices.data
      ? t('{n} deutsche Stimmen im Gemini-Katalog.', { n: list.length })
      : t('Stimmen aus dem Gemini-Katalog — passend zur Sprache der Oberfläche.')
  // Gespeicherte Stimme, die (noch) nicht in der Liste steht, trotzdem zeigen.
  const extra = curVoice && !list.some((v) => v.id === curVoice)

  const preview = async () => {
    setNote('…')
    try {
      await say(
        t('Hallo {u}, ich bin {a}. So klinge ich mit dieser Stimme.', {
          u: boot.user || t('Du'),
          a: boot.assistant,
        }),
        { voice: curVoice, model: tts.model, style, owner: 'settings-preview' },
      )
      setNote('')
    } catch (e) {
      stopSay()
      setNote('⚠ ' + trServer((e as Error).message))
    }
  }

  return (
    <Section id="vorlesen">
      <div className={s.d} style={{ marginBottom: 10 }}>
        {rich(
          t(
            'Antworten per <b>Gemini TTS</b> vorlesen lassen — der 🔊 neben dem Namen über jeder Antwort. Braucht einen Gemini-Key (kostenlos auf aistudio.google.com/apikey) — derselbe wie für den Gemini-Chat.',
          ),
        )}
      </div>
      <div style={{ marginBottom: 10 }}>
        <button type="button" className={s.btn} onClick={() => openDialog('providers')}>
          {t('🔑 Gemini-Key eintragen…')}
        </button>
      </div>
      <div className={s.row}>
        <label>
          <input
            type="checkbox"
            checked={!!tts.auto}
            onChange={(e) => void save({ tts: { auto: e.target.checked } })}
          />
          <span>
            <span className={s.t}>{t('Antworten automatisch vorlesen')}</span>
            <span className={s.d}>
              {t('Jede fertige Antwort im offenen Chat wird sofort gesprochen.')}
            </span>
          </span>
        </label>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Modell')}</span>
          <span className={s.d}>
            {rich(
              t(
                '<b>Flash-Lite</b> ist schneller und schont das Kontingent, <b>Flash</b> klingt ausdrucksstärker.',
              ),
            )}
          </span>
          <span className={s.actions}>
            <select
              className={s.btn}
              value={tts.model || MODELS[0]!.v}
              onChange={(e) => void save({ tts: { model: e.target.value } })}
            >
              {MODELS.map((m) => (
                <option key={m.v} value={m.v}>
                  {m.l}
                </option>
              ))}
            </select>
          </span>
        </span>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Stimme')}</span>
          <span className={s.d}>{info}</span>
          <span className={s.actionsFlex}>
            <select
              className={s.btn}
              value={curVoice || list[0]?.id || ''}
              onChange={(e) => void save({ tts: { voice: { [lang]: e.target.value } } })}
            >
              {extra && <option value={curVoice}>{curVoice}</option>}
              {list.map((v) => (
                <option key={v.id} value={v.id} title={v.description || ''}>
                  {voiceLabel(v)}
                </option>
              ))}
            </select>
            <button type="button" className={s.btn} onClick={() => void preview()}>
              {t('▶ Hörprobe')}
            </button>
            <Note text={note} />
          </span>
        </span>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Sprechweise')}</span>
          <span className={s.d}>
            {t('Optionale Regieanweisung, z. B. „locker und freundlich, etwas zügig“.')}
          </span>
          {/* Beim Verlassen speichern, nicht bei jedem Tastendruck. */}
          <input
            className={`${s.btn} ${s.styleIn}`}
            maxLength={200}
            placeholder={t('leer = natürlich')}
            value={style}
            onChange={(e) => setStyle(e.target.value)}
            onBlur={() => {
              if (style !== (tts.style?.[lang] ?? ''))
                void save({ tts: { style: { [lang]: style } } })
            }}
          />
        </span>
      </div>
    </Section>
  )
}
