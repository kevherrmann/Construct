import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Nachricht, Person } from '@/api/team'
import { Markdown } from '@/components/chat/Markdown'
import { useSettings } from '@/stores/settings'
import { Avatar } from '../personal/Person'
import s from './Auftraege.module.css'

const ART: Record<string, string> = {
  auftrag: 'beauftragt',
  frage: 'fragt',
  antwort: 'antwortet',
  ergebnis: 'liefert an',
  notiz: 'notiert',
  einwurf: 'wirft ein bei',
  gesagt: 'sagt',
}

/** Eine Zeile im Auftragsverlauf: Absender → Empfänger im Kopf, Farbe aus der
 *  Personalakte. Auch eine echte Lieferung darf lang sein — sie muss nur nicht
 *  ungefragt in voller Länge dastehen (ab 900 Zeichen eingeklappt). */
export function NachrichtKarte({ e, leute }: { e: Nachricht; leute: Record<string, Person> }) {
  const { t } = useTranslation()
  const nutzer = useSettings((st) => st.boot.user || st.settings.names.user) || t('Du')
  const [offen, setOffen] = useState(false)
  if (e.art === 'zugestellt') return null
  if (e.art === 'system')
    return (
      <div className={`${s.notiz} ${e.bremse ? s.bremse : ''}`}>
        {e.bremse ? '⏸ ' : '· '}
        {e.text}
      </div>
    )
  // 'gesagt' ist, was jemand während seines Zugs gesprochen hat: genau der Text
  // seiner Sprechblase im Raum. Er steht deshalb wie jede Nachricht im Verlauf;
  // als zugeklappte Arbeitsspur sah das Protokoll anders aus als die Blase.
  const kevin = e.von === 'kevin'
  const p: Person = kevin
    ? { name: nutzer, title: '', color: '126,231,135', avatar: '' }
    : (leute[e.von] ?? { name: e.von || t('System'), title: '', color: '126,231,135', avatar: '' })
  const ziel = e.an === 'kevin' ? nutzer : e.an ? (leute[e.an]?.name ?? e.an) : ''
  const art = ART[e.art] ?? ''
  const lang = e.text.length > 900
  return (
    <div
      className={`${s.zeile} ${kevin ? s.user : ''}`}
      style={{ ['--accent-rgb' as string]: p.color }}
    >
      <Avatar p={p} groesse={32} />
      <div className={s.col}>
        <div className={s.who}>
          {p.name.toUpperCase()}
          {ziel ? ` · ${t(art)} ${ziel}` : art ? ` · ${t(art)}` : ''}
          {e.art === 'auftrag' && e.groesse && e.groesse !== 'normal' ? ` · ${e.groesse}` : ''}
        </div>
        <div className={`${s.bubble} ${lang && !offen ? s.kurz : ''}`}>
          <Markdown text={e.text} />
        </div>
        {lang && (
          <button type="button" className={s.mehr} onClick={() => setOffen(!offen)}>
            {offen ? `▾ ${t('einklappen')}` : `▸ ${t('ganze Nachricht anzeigen')}`}
          </button>
        )}
        {!!e.dateien?.length && (
          <div className={s.dateien}>
            <span className={s.lbl}>{t('GEÄNDERT')}</span>
            {e.dateien.map((f) => (
              <a
                key={f}
                href={`/api/file?path=${encodeURIComponent(f)}`}
                target="_blank"
                rel="noreferrer"
                title={f}
              >
                {f.split('/').pop() || f}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
