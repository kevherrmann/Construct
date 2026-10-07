import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useFolders } from '@/api/chat'
import {
  projektName,
  SPALTEN,
  SPALTEN_NAME,
  useBoard,
  useTicketActions,
  type Spalte,
  type Ticket,
} from '@/api/tickets'
import { Dialog } from '@/components/dialogs/Dialog'
import { useSessionOeffnen } from '@/hooks/useSessionOeffnen'
import { kurzzeit } from './format'
import { useTicketsAnsicht } from './store'
import s from './Tickets.module.css'

/** Projekte zur Auswahl: die vom Board und die Ordner des Workspace. */
function useProjekte(aktuell: string) {
  const board = useBoard().data
  const ordner = useFolders().data ?? []
  const pfade = new Set([...(board?.projekte ?? []).map((p) => p.pfad), ...ordner])
  if (aktuell) pfade.add(aktuell)
  return [...pfade].sort((a, b) => projektName(a).localeCompare(projektName(b)))
}

function Formular({ karte, onDone }: { karte: Ticket | null; onDone?: () => void }) {
  const { t } = useTranslation()
  const zu = useTicketsAnsicht((st) => st.zu)
  const filter = useTicketsAnsicht((st) => st.projekt)
  const act = useTicketActions()
  const oeffnen = useSessionOeffnen(onDone)
  const [titel, setTitel] = useState(karte?.titel ?? '')
  const [text, setText] = useState(karte?.text ?? '')
  const [projekt, setProjekt] = useState(karte?.projekt ?? filter ?? '')
  const [spalte, setSpalte] = useState<Spalte>(karte?.spalte ?? 'neu')
  const projekte = useProjekte(projekt)
  const geaendert =
    !karte || titel !== karte.titel || text !== karte.text || projekt !== karte.projekt

  const speichern = () => {
    if (!titel.trim()) return
    if (karte)
      act.aendern.mutate(
        { nr: karte.nr, titel: titel.trim(), text, projekt },
        { onSuccess: () => zu() },
      )
    else
      act.anlegen.mutate({ titel: titel.trim(), text, projekt, spalte }, { onSuccess: () => zu() })
  }
  const schieben = (sp: Spalte) => {
    setSpalte(sp)
    if (karte && sp !== karte.spalte) act.aendern.mutate({ nr: karte.nr, spalte: sp })
  }

  return (
    <div className={s.form}>
      <label className={s.lbl}>{t('TITEL')}</label>
      <input
        className={s.feld}
        autoFocus={!karte}
        maxLength={80}
        value={titel}
        onChange={(e) => setTitel(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && speichern()}
      />
      <label className={s.lbl}>{t('BESCHREIBUNG')}</label>
      <textarea
        className={s.text}
        value={text}
        placeholder={t('Was soll passieren, worauf ist zu achten?')}
        onChange={(e) => setText(e.target.value)}
      />
      <label className={s.lbl}>{t('PROJEKT')}</label>
      <select className={s.feld} value={projekt} onChange={(e) => setProjekt(e.target.value)}>
        <option value="">—</option>
        {projekte.map((p) => (
          <option key={p} value={p}>
            {projektName(p)} · {p}
          </option>
        ))}
      </select>
      <label className={s.lbl}>{t('SPALTE')}</label>
      <div className={s.pillen}>
        {SPALTEN.map((sp) => (
          <button
            key={sp}
            type="button"
            className={`${s.pille} ${spalte === sp ? s.an : ''}`}
            onClick={() => schieben(sp)}
          >
            {t(SPALTEN_NAME[sp])}
          </button>
        ))}
      </div>

      {karte && karte.commits.length > 0 && (
        <>
          <label className={s.lbl}>{t('COMMITS')}</label>
          <div className={s.commits}>
            {karte.commits.map((c) => (
              <div key={c.sha} className={s.commit} title={`${c.repo} · ${c.branch}`}>
                <span className={s.sha}>{c.sha.slice(0, 8)}</span>
                <span className={s.betreff}>{c.betreff}</span>
                <span className={s.leise}>{c.gepusht ? t('gepusht') : c.branch}</span>
              </div>
            ))}
          </div>
        </>
      )}
      {karte && (
        <div className={s.leise}>
          {t('Angelegt {zeit}', { zeit: kurzzeit(karte.erstellt) })}
          {karte.auftrag && ` · 🏢 ${t('Die Firma arbeitet daran')}`}
        </div>
      )}

      <div className={s.aktionen}>
        <button
          type="button"
          className={s.knopf}
          disabled={!titel.trim() || !geaendert || act.anlegen.isPending}
          onClick={speichern}
        >
          {karte ? t('SPEICHERN') : t('ANLEGEN')}
        </button>
        {karte?.session && (
          <button
            type="button"
            className={s.knopf}
            onClick={() => {
              zu()
              oeffnen(karte.session, karte.projekt, karte.uuid || undefined)
            }}
          >
            💬 {t('Im Chat zeigen')}
          </button>
        )}
        {karte && (
          <button
            type="button"
            className={`${s.knopf} ${s.gefahr}`}
            onClick={() => {
              if (confirm(t('Ticket T-{nr} löschen?', { nr: karte.nr })))
                act.loeschen.mutate(karte.nr, { onSuccess: () => zu() })
            }}
          >
            {t('Löschen')}
          </button>
        )}
      </div>
    </div>
  )
}

/** Eine Karte ansehen und bearbeiten, oder eine neue anlegen. */
export function TicketDialog({ onDone }: { onDone?: () => void }) {
  const { t } = useTranslation()
  const { offen, zu } = useTicketsAnsicht()
  const board = useBoard().data
  const karte =
    typeof offen === 'number' ? (board?.tickets.find((x) => x.nr === offen) ?? null) : null
  const auf = offen === 'neu' || !!karte
  return (
    <Dialog open={auf} onClose={zu} title={karte ? `T-${karte.nr}` : t('Neues Ticket')} wide>
      {/* key: eine andere Karte beginnt mit frischen Feldern */}
      {auf && <Formular key={karte?.nr ?? 'neu'} karte={karte} onDone={onDone} />}
    </Dialog>
  )
}
