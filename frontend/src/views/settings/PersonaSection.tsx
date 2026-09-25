import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { savePersona, usePersona, type Persona, type PersonaKey } from '@/api/settings'
import { rich } from '@/lib/rich'
import { Note, Section } from './parts'
import s from './Settings.module.css'

// Ungespeicherte Eingaben überleben den Reiter- und Ansichtswechsel (wie in
// der alten Oberfläche) — sonst ist Text weg, und man merkt es erst zu spät.
const drafts: Partial<Persona> = {}
let lastTab: PersonaKey = 'soul'

export function PersonaSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = usePersona()
  const [tab, setTab] = useState<PersonaKey>(lastTab)
  const [, bump] = useState(0)
  const [note, setNote] = useState('')

  useEffect(() => {
    if (!note || note === '…') return
    const id = setTimeout(() => setNote(''), 2600)
    return () => clearTimeout(id)
  }, [note])

  const value = drafts[tab] ?? q.data?.[tab] ?? ''
  const edit = (v: string) => {
    drafts[tab] = v
    bump((n) => n + 1)
  }
  const switchTab = (k: PersonaKey) => {
    lastTab = k
    setTab(k)
  }
  const save = async () => {
    setNote('…')
    try {
      await savePersona({ [tab]: value })
      qc.setQueryData<Persona>(['persona'], (old) => ({
        ...(old ?? { soul: '', user: '' }),
        [tab]: value,
      }))
      delete drafts[tab]
      setNote(t('✓ gespeichert — gilt ab der nächsten Nachricht'))
    } catch {
      setNote(t('⚠ nicht gespeichert'))
    }
  }

  return (
    <Section id="charakter">
      <div className={s.d} style={{ marginBottom: 10 }}>
        {rich(
          t(
            'Beides wird bei <b>jeder</b> Nachricht mitgelesen — auch von fremden Modellen. <b>Charakter</b> beschreibt, wer der Assistent ist; <b>Über dich</b>, was er über dich wissen soll. Reiner Text, Markdown erlaubt.',
          ),
        )}
      </div>
      <div className={s.tabs}>
        <button
          type="button"
          className={`${s.tab} ${tab === 'soul' ? s.on : ''}`}
          onClick={() => switchTab('soul')}
        >
          {t('Charakter (SOUL.md)')}
        </button>
        <button
          type="button"
          className={`${s.tab} ${tab === 'user' ? s.on : ''}`}
          onClick={() => switchTab('user')}
        >
          {t('Über dich (USER.md)')}
        </button>
      </div>
      <textarea
        className={s.area}
        spellCheck={false}
        placeholder={t('wird geladen…')}
        value={value}
        onChange={(e) => edit(e.target.value)}
      />
      <div className={s.actionsFlex} style={{ flexWrap: 'nowrap' }}>
        <button type="button" className={s.btn} onClick={() => void save()}>
          {t('Speichern')}
        </button>
        <Note text={note} />
      </div>
    </Section>
  )
}
