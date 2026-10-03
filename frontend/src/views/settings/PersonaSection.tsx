import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useProviders } from '@/api/providers'
import { savePersona, usePersona, type Persona, type PersonaKey } from '@/api/settings'
import { rich } from '@/lib/rich'
import { useSettings } from '@/stores/settings'
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
  const assistant = useSettings((x) => x.boot.assistant)
  // Den Reiter für lokale Modelle gibt es nur, wenn eins eingerichtet ist.
  const lokalDa = (useProviders().data ?? []).some(
    (p) => (p.id === 'bonsai' || p.id === 'ollama') && p.configured && p.models.length > 0,
  )
  const [wahl, setTab] = useState<PersonaKey>(lastTab)
  const tab: PersonaKey = wahl === 'lokal' && !lokalDa ? 'soul' : wahl
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
        ...(old ?? { soul: '', user: '', lokal: '' }),
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
        {lokalDa && (
          <button
            type="button"
            className={`${s.tab} ${tab === 'lokal' ? s.on : ''}`}
            onClick={() => switchTab('lokal')}
          >
            {t('Lokale Modelle')}
          </button>
        )}
      </div>
      {tab === 'lokal' && (
        <div className={s.d} style={{ margin: '8px 0' }}>
          {rich(
            t(
              'Eigene Persona <b>nur für Bonsai und Ollama</b> — zum Ausprobieren, {a} bleibt davon unberührt. Ersetzt Charakter und „Über dich“, Kalender und Werkzeuge bleiben. Leer = dieselbe Persona wie {a}. Für einen sauberen Rollenwechsel eine <b>neue Session</b> starten: in einer laufenden Unterhaltung spielt ein kleines Modell oft die alte Rolle weiter.',
              { a: assistant },
            ),
          )}
        </div>
      )}
      <textarea
        className={s.area}
        spellCheck={false}
        placeholder={
          tab === 'lokal'
            ? t('z. B. „Du bist ein grummeliger Pirat, der jede Antwort mit Arrr beginnt.“')
            : t('wird geladen…')
        }
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
