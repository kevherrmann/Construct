import { useEffect, useLayoutEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { merkeGesehen, useAuftrag, type Person } from '@/api/team'
import { Einwurf } from './AuftragAnsicht'
import { Eskalation } from './Eskalation'
import { LiveZug } from './LiveZug'
import { NachrichtKarte } from './NachrichtKarte'
import { useAuftraegeAnsicht } from './store'
import { ZUSTAND } from './zustand'
import s from './Auftraege.module.css'

const GRAU: Person = { name: '?', title: '', color: '126,231,135', avatar: '' }

/** Der ganze Verlauf eines Auftrags für das Protokoll im Raum: wer wann was an wen
 *  geschrieben hat, dazu der Zug, der gerade läuft. Wie ein Chat bleibt die Ansicht
 *  unten kleben, solange du nicht hochgescrollt hast. Antworten (Rückfrage, Einwurf)
 *  geht von hier aus genauso wie in den Aufträgen. */
export function AuftragProtokoll({ id }: { id: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: d, isError } = useAuftrag(id)
  const zurSession = useAuftraegeAnsicht((st) => st.zurSession)
  const verlauf = d?.verlauf.filter((e) => e.art !== 'zugestellt') ?? []
  const anzahl = verlauf.length
  const inhalt = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!d) return
    merkeGesehen(id, anzahl)
    void qc.invalidateQueries({ queryKey: ['team', 'auftraege'] })
  }, [id, anzahl, d, qc])

  // Unten kleben: Wer am Ende steht, bleibt dort, wenn Nachrichten dazukommen oder
  // der laufende Zug wächst. Wer hochgescrollt hat, wird nicht zurückgerissen.
  const geladen = !!d
  useLayoutEffect(() => {
    const el = inhalt.current
    const box = el?.closest<HTMLElement>('[data-scroll]')
    if (!el || !box) return
    let amEnde = true
    const nachUnten = () => {
      box.style.scrollBehavior = 'auto'
      box.scrollTop = box.scrollHeight
      box.style.scrollBehavior = ''
    }
    nachUnten()
    const merke = () => {
      amEnde = box.scrollHeight - box.scrollTop - box.clientHeight < 40
    }
    box.addEventListener('scroll', merke, { passive: true })
    const ro = new ResizeObserver(() => amEnde && nachUnten())
    ro.observe(el)
    return () => {
      box.removeEventListener('scroll', merke)
      ro.disconnect()
    }
  }, [id, geladen])

  const zumChat = (
    <button type="button" className={s.knopf} onClick={zurSession}>
      ‹ {t('ZUM CHAT')}
    </button>
  )
  if (isError && !d)
    return (
      <div className={s.wrap}>
        <div className={s.leiste}>{zumChat}</div>
        <div className={s.fehler}>{t('Auftrag gerade nicht ladbar — nochmal draufklicken.')}</div>
      </div>
    )
  if (!d) return <div className={s.wrap}>⟲ …</div>
  const tk = d.ticket
  const leute = d.agents
  const ia = tk.status === 'laeuft' ? tk.in_arbeit : null
  const arbeitetSlug = ia ? (verlauf.find((e) => e.id === ia.msg_id)?.an ?? '') : ''
  const runId = ia?.run_id ?? ''
  const z = ZUSTAND[tk.status]
  const laeuftNoch = tk.status !== 'fertig' && tk.status !== 'abgebrochen'

  return (
    <div className={s.wrap} ref={inhalt}>
      <div className={s.leiste}>
        {zumChat}
        <span className={s.leisteTitel}>🎫 {tk.titel}</span>
        <span className={`${s.chip} ${z.art ? s[z.art] : ''}`}>{z.zeichen}</span>
      </div>
      {verlauf.map((e) => (
        <NachrichtKarte key={e.id} e={e} leute={leute} />
      ))}
      {arbeitetSlug && runId && (
        <LiveZug
          key={runId}
          runId={runId}
          person={leute[arbeitetSlug] ?? { ...GRAU, name: arbeitetSlug }}
        />
      )}
      <Eskalation auftrag={tk} leute={leute} />
      <Einwurf id={id} offen={laeuftNoch} />
    </div>
  )
}
