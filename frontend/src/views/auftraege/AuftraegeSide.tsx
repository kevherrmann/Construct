import { useTranslation } from 'react-i18next'
import { useAuftragActions, useAuftraege, ungelesen, type AuftragKurz } from '@/api/team'
import { useUi } from '@/stores/ui'
import { useAuftraegeAnsicht } from './store'
import { ZUSTAND } from './zustand'
import s from './Auftraege.module.css'

function Zeile({ auftrag }: { auftrag: AuftragKurz }) {
  const { t } = useTranslation()
  const { auswahl, oeffne: oeffneAuftrag, schliessen } = useAuftraegeAnsicht()
  const zu = useUi((st) => st.setSideOpen)
  const oeffne = (id: string) => (oeffneAuftrag(id), zu(false))
  const loeschen = useAuftragActions(auftrag.id).loeschen
  const z = ZUSTAND[auftrag.status]
  const n = auswahl === auftrag.id ? 0 : ungelesen(auftrag)
  return (
    <div
      role="button"
      tabIndex={0}
      className={`${s.tk} ${z.art ? s[z.art] : ''} ${auswahl === auftrag.id ? s.on : ''} ${n > 0 ? s.neu : ''}`}
      onClick={() => oeffne(auftrag.id)}
      onKeyDown={(e) => e.key === 'Enter' && oeffne(auftrag.id)}
    >
      <span>{z.zeichen}</span>
      <span className={s.tn}>{auftrag.titel}</span>
      {n > 0 && <span className={s.nz}>{n}</span>}
      <span className={s.tb}>{auftrag.verbraucht.hops} ⇢</span>
      <button
        type="button"
        className={`${s.tb} ${s.del}`}
        title={t('löschen')}
        onClick={(e) => {
          e.stopPropagation()
          if (confirm(t('Auftrag „{t}“ mit ganzem Verlauf löschen?', { t: auftrag.titel })))
            loeschen.mutate(undefined, { onSuccess: () => auswahl === auftrag.id && schliessen() })
        }}
      >
        ✕
      </button>
    </div>
  )
}

// Seitenleiste: neuer Auftrag, darunter alle Aufträge mit Zustand und Ungelesenem.
export function AuftraegeSide() {
  const { t } = useTranslation()
  const { data, isPending } = useAuftraege()
  const neuer = useAuftraegeAnsicht((st) => st.neu)
  const zu = useUi((st) => st.setSideOpen)
  const neu = () => (neuer(), zu(false))
  const auswahl = useAuftraegeAnsicht((st) => st.auswahl)
  return (
    <div>
      <button type="button" className={`${s.add} ${auswahl === 'neu' ? s.on : ''}`} onClick={neu}>
        {t('＋ NEUER AUFTRAG')}
      </button>
      {!isPending && !data?.length && <div className={s.hint}>{t('Noch keine Aufträge.')}</div>}
      {data?.map((x) => (
        <Zeile key={x.id} auftrag={x} />
      ))}
    </div>
  )
}
