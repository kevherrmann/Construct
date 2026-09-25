import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { rich } from '@/lib/rich'
import { useSettings } from '@/stores/settings'
import { Section } from './parts'
import { pickUpload } from './helpers'
import s from './Settings.module.css'

type Who = 'user' | 'assistant'

export function NamesSection() {
  const { t } = useTranslation()
  const names = useSettings((st) => st.settings.names)
  const avatars = useSettings((st) => st.settings.avatars)
  const save = useSettings((st) => st.save)
  const [user, setUser] = useState(names?.user ?? '')
  const [asst, setAsst] = useState(names?.assistant ?? '')
  const file = useRef<HTMLInputElement>(null)
  const who = useRef<Who>('user')

  const pick = (w: Who) => {
    who.current = w
    file.current?.click()
  }
  const upload = async (f: File | undefined) => {
    const url = await pickUpload(f, t('Upload fehlgeschlagen'))
    if (url) void save({ avatars: { [who.current]: url } })
  }

  const av = avatars ?? { user: '', assistant: '' }
  const initial = (names?.user || '?').slice(0, 1).toUpperCase()

  return (
    <Section id="namen">
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Wie soll ich dich nennen?')}</span>
          <span className={s.d}>
            {t(
              'Steht im Chat über deinen Nachrichten und wird den Modellen mitgegeben. Leer lassen geht auch — dann bleibt es unpersönlich.',
            )}
          </span>
          <span className={s.actions} style={{ marginTop: 8 }}>
            {/* Beim Verlassen speichern, nicht bei jedem Tastendruck — sonst
                schreibt jeder Buchstabe eine Datei. */}
            <input
              className={s.in}
              maxLength={40}
              placeholder={t('dein Name')}
              value={user}
              onChange={(e) => setUser(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
              onBlur={() => user !== (names?.user ?? '') && void save({ names: { user } })}
            />
          </span>
        </span>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Wie heißt der Assistent?')}</span>
          <span className={s.d}>
            {rich(
              t(
                'CONSTRUCT ist der Ort, er ist die Person darin. Wer ihn umbenennt, sollte auch <code>SOUL.md</code> anpassen — dort steht sein Charakter.',
              ),
            )}
          </span>
          <span className={s.actions} style={{ marginTop: 8 }}>
            <input
              className={s.in}
              maxLength={40}
              placeholder="Cody"
              value={asst}
              onChange={(e) => setAsst(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
              onBlur={() =>
                asst !== (names?.assistant ?? '') && void save({ names: { assistant: asst } })
              }
            />
          </span>
        </span>
      </div>
      <div className={s.row}>
        <span className={s.grow}>
          <span className={s.t}>{t('Bilder')}</span>
          <span className={s.d}>
            {t(
              'Erscheinen im Chat neben den Nachrichten. Ohne eigenes Bild steht bei dir der Anfangsbuchstabe.',
            )}
          </span>
          <span className={s.avPick}>
            <span
              className={s.avPrev}
              style={av.user ? { backgroundImage: `url("${av.user}")` } : undefined}
            >
              {av.user ? '' : initial}
            </span>
            <button type="button" className={s.btn} onClick={() => pick('user')}>
              {t('Deins wählen…')}
            </button>
            <button
              type="button"
              className={s.btn}
              onClick={() => void save({ avatars: { user: '' } })}
            >
              ✕
            </button>
          </span>
          <span className={s.avPick}>
            <span
              className={s.avPrev}
              style={{ backgroundImage: `url("${av.assistant || '/static/cody.png'}")` }}
            />
            <button type="button" className={s.btn} onClick={() => pick('assistant')}>
              {t('Seins wählen…')}
            </button>
            <button
              type="button"
              className={s.btn}
              onClick={() => void save({ avatars: { assistant: '' } })}
            >
              ✕
            </button>
          </span>
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
        </span>
      </div>
      <div className={s.d} style={{ marginTop: 6 }}>
        {t('Namen wirken nach dem Neuladen der Seite.')}
      </div>
    </Section>
  )
}
