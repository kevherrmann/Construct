import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettings } from '@/stores/settings'
import { Section } from './parts'
import s from './Settings.module.css'

type Klang = { effekte: boolean; musik: boolean; lautstaerke: number }

// Klänge gibt es nur im Construct-Raum (lib/klang.ts). Der Regler wirkt beim
// Ziehen sofort, gespeichert wird beim Loslassen — wie beim Abdunkeln.
export function KlangSection() {
  const { t } = useTranslation()
  const sound = useSettings((st) => st.settings.sound)
  const save = useSettings((st) => st.save)
  const preview = useSettings((st) => st.preview)
  const [vol, setVol] = useState(sound.lautstaerke)
  const pending = useRef<number | null>(null)

  const apply = (patch: Partial<Klang>) => void save({ sound: patch })
  const slide = (v: number) => {
    setVol(v)
    pending.current = v
    preview({ sound: { lautstaerke: v } })
  }
  const commit = () => {
    if (pending.current == null) return
    apply({ lautstaerke: pending.current })
    pending.current = null
  }
  const commitRef = useRef(commit)
  useEffect(() => {
    commitRef.current = commit
  })
  useEffect(() => () => commitRef.current(), [])

  const schalter: { k: 'effekte' | 'musik'; title: string; d: string }[] = [
    {
      k: 'effekte',
      title: t('Geräusche'),
      d: t('Tippen, Öffnen und Schließen, die tickende Uhr, Cody an der Tastatur.'),
    },
    {
      k: 'musik',
      title: t('Coding-Musik'),
      d: t('Leiser Lo-Fi-Beat im Hintergrund — wird live erzeugt, wiederholt sich nicht.'),
    },
  ]

  return (
    <Section id="klang">
      <div className={s.d} style={{ marginBottom: 10 }}>
        {t('Nur im Construct-Raum. Der Browser gibt Ton erst nach dem ersten Klick frei.')}
      </div>
      {schalter.map((x) => (
        <div className={s.row} key={x.k}>
          <label>
            <input
              type="checkbox"
              checked={!!sound[x.k]}
              onChange={(e) => apply({ [x.k]: e.target.checked })}
            />
            <span>
              <span className={s.t}>{x.title}</span>
              <span className={s.d}>{x.d}</span>
            </span>
          </label>
        </div>
      ))}
      <div style={{ marginTop: 12 }}>
        <label className={s.d} htmlFor="klangVol">
          {t('Lautstärke:')} <b>{vol} %</b>
        </label>
        <input
          id="klangVol"
          type="range"
          min={0}
          max={100}
          className={s.slider}
          value={vol}
          onChange={(e) => slide(+e.target.value)}
          onPointerUp={commit}
          onKeyUp={commit}
          onBlur={commit}
        />
      </div>
    </Section>
  )
}
