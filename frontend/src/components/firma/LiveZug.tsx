import { useTranslation } from 'react-i18next'
import type { Person } from '@/api/team'
import { BlockView } from '@/components/chat/Message'
import { Avatar } from '@/views/personal/Person'
import { useLiveZug } from './useLiveZug'
import s from './Firma.module.css'

/** Der laufende Zug einer Person — dieselbe Darstellung wie im Chat (Text,
 *  Werkzeugkarten, Ergebnisse), ohne dessen Sitzungsverwaltung. Der Server
 *  spielt beim Verbinden alles bisher Passierte nach: man steigt mittendrin ein
 *  und sieht trotzdem den ganzen Zug. */
export function LiveZug({ runId, person }: { runId: string; person: Person }) {
  const { t } = useTranslation()
  const { lauf, weg } = useLiveZug(runId)

  if (weg)
    return (
      <div className={s.notiz}>
        ⚠ {t('Der Zug ist nicht mehr abrufbar — er ist fertig und weggeräumt.')}
      </div>
    )
  return (
    <div className={s.zeile} style={{ ['--accent-rgb' as string]: person.color }}>
      <Avatar p={person} groesse={32} aktiv />
      <div className={s.col}>
        <div className={s.who}>
          {person.name.toUpperCase()} · {t('arbeitet gerade')}
        </div>
        <div className={s.bubble}>
          {lauf.items.map((it) =>
            it.kind === 'bot'
              ? it.blocks.map((b, i) => <BlockView key={`${it.id}:${i}`} block={b} />)
              : null,
          )}
        </div>
      </div>
    </div>
  )
}
