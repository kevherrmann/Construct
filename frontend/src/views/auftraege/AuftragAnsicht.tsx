import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import {
  merkeGesehen,
  useAuftrag,
  useAuftragActions,
  type AuftragDetail,
  type Person,
} from '@/api/team'
import { Avatar } from '../personal/Person'
import { besetzung, type Knoten } from './besetzung'
import { Eskalation } from './Eskalation'
import { LiveZug } from './LiveZug'
import { NachrichtKarte } from './NachrichtKarte'
import { useAuftraegeAnsicht } from './store'
import { ZUSTAND } from './zustand'
import s from './Auftraege.module.css'

const GRAU: Person = { name: '?', title: '', color: '126,231,135', avatar: '' }

function Karte({ k, leute }: { k: Knoten; leute: Record<string, Person> }) {
  const { t } = useTranslation()
  const sichtWechseln = useAuftraegeAnsicht((st) => st.sichtWechseln)
  const p = leute[k.slug] ?? { ...GRAU, name: k.slug }
  const status = k.arbeitet
    ? t('arbeitet …')
    : k.geliefert
      ? t('geliefert an {n}', {
          n: k.geliefert === 'kevin' ? t('dich') : (leute[k.geliefert]?.name ?? k.geliefert),
        })
      : k.stumm
        ? t('beauftragt')
        : ''
  return (
    <div className={s.otknoten}>
      <button
        type="button"
        className={s.crewkarte}
        style={{ ['--accent-rgb' as string]: p.color }}
        title={`${p.name}${p.title ? ` · ${p.title}` : ''} — ${t('anklicken')}`}
        onClick={() => sichtWechseln(k.slug)}
      >
        <Avatar p={p} groesse={46} aktiv={k.arbeitet} />
        <span className={s.crewnam}>{p.name.toUpperCase()}</span>
        <span className={`${s.crewst} ${k.arbeitet ? s.an : ''}`}>{status}</span>
      </button>
      {k.kinder.length > 0 && (
        <div className={s.otkinder}>
          {k.kinder.map((c) => (
            <Karte key={c.slug} k={c} leute={leute} />
          ))}
        </div>
      )}
    </div>
  )
}

function Stand({ d, ende }: { d: AuftragDetail; ende: number }) {
  const { t } = useTranslation()
  const v = d.ticket.verbraucht
  // Die Laufzeit tickt, ohne dass sich sonst etwas ändert — Zeit gehört in einen
  // Zustand, nicht in die Berechnung beim Zeichnen.
  const [jetzt, setJetzt] = useState(() => Date.now())
  useEffect(() => {
    const i = setInterval(() => setJetzt(Date.now()), 30_000)
    return () => clearInterval(i)
  }, [])
  // Ein fertiger oder abgebrochener Auftrag zählt nicht weiter: seine Laufzeit reicht bis zur
  // letzten Nachricht.
  const aus = d.ticket.status === 'fertig' || d.ticket.status === 'abgebrochen'
  const min = Math.max(0, Math.round(((aus && ende ? ende : jetzt / 1000) - (v.start || 0)) / 60))
  return (
    <div className={s.stand}>
      <span>
        {t('Schritte')} <b>{v.hops}</b>
      </span>
      <span>
        {t('Laufzeit')} <b>{min} min</b>
      </span>
    </div>
  )
}

/** Einwurf: landet im laufenden Zug, wenn gerade jemand arbeitet — sonst wird er eine
 *  normale Nachricht (und wartet der Auftrag auf den Nutzer, ist es eine Antwort). */
function Einwurf({ id, offen }: { id: string; offen: boolean }) {
  const { t } = useTranslation()
  const act = useAuftragActions(id)
  const [text, setText] = useState('')
  const [meldung, setMeldung] = useState('')
  if (!offen) return null
  const los = () => {
    if (!text.trim()) return
    setMeldung('')
    act.say.mutate(
      { text: text.trim() },
      {
        onSuccess: (j) => {
          setText('')
          setMeldung(j.wohin === 'laufender Zug' ? t('✓ im laufenden Zug') : t('✓ eingereiht'))
        },
        onError: (e) => setMeldung(`⚠ ${e.message}`),
      },
    )
  }
  return (
    <div className={s.einwurf}>
      <textarea
        className={s.text}
        value={text}
        placeholder={t(
          'Einwurf an die Firma — landet im laufenden Zug, wenn gerade jemand arbeitet',
        )}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            los()
          }
        }}
      />
      <div className={s.btns}>
        <button type="button" className={s.knopf} disabled={act.say.isPending} onClick={los}>
          {t('➤ EINWERFEN')}
        </button>
        <span className={s.msg}>{meldung}</span>
      </div>
    </div>
  )
}

export function AuftragAnsicht({ id }: { id: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: d, isError } = useAuftrag(id)
  const { sicht, sichtWechseln } = useAuftraegeAnsicht()
  const verlauf = d?.verlauf.filter((e) => e.art !== 'zugestellt') ?? []
  const anzahl = verlauf.length

  // Gesehen = so viele Nachrichten, wie jetzt da sind. Danach die Liste neu
  // zeichnen lassen, damit das Ungelesen-Zeichen verschwindet.
  useEffect(() => {
    if (!d) return
    merkeGesehen(id, anzahl)
    void qc.invalidateQueries({ queryKey: ['team', 'auftraege'] })
  }, [id, anzahl, d, qc])

  if (isError && !d)
    return (
      <div className={s.wrap}>
        <div className={s.fehler}>{t('Auftrag gerade nicht ladbar — nochmal draufklicken.')}</div>
      </div>
    )
  if (!d) return <div className={s.wrap}>⟲ …</div>
  const tk = d.ticket
  const leute = d.agents
  const ia = tk.status === 'laeuft' ? tk.in_arbeit : null
  const arbeitetSlug = ia ? (verlauf.find((e) => e.id === ia.msg_id)?.an ?? '') : ''
  const runId = ia?.run_id ?? ''
  const baum = besetzung(tk, verlauf, arbeitetSlug)
  const ende = [...verlauf].reverse().find((e) => e.art === 'ergebnis' && e.an === 'kevin')
  const z = ZUSTAND[tk.status]
  const laeuftNoch = tk.status !== 'fertig' && tk.status !== 'abgebrochen'

  const zurueck = (
    <button type="button" className={s.zurueck} onClick={() => sichtWechseln('uebersicht')}>
      ‹ {t('zurück zur Übersicht')}
    </button>
  )
  let buehne: React.ReactNode
  if (sicht === 'verlauf')
    buehne = (
      <>
        {zurueck}
        {verlauf.map((e) => (
          <NachrichtKarte key={e.id} e={e} leute={leute} />
        ))}
      </>
    )
  else if (sicht !== 'uebersicht') {
    const p = leute[sicht] ?? { ...GRAU, name: sicht }
    const seins = verlauf.filter((e) => e.von === sicht || e.an === sicht)
    const arbeitet = arbeitetSlug === sicht
    buehne = (
      <>
        {zurueck}
        <div className={s.personkopf} style={{ ['--accent-rgb' as string]: p.color }}>
          <Avatar p={p} groesse={40} aktiv={arbeitet} />
          <div>
            <b>{p.name}</b>
            <i>{p.title}</i>
          </div>
          {arbeitet && <span className={s.leise}>{t('arbeitet gerade')}</span>}
        </div>
        {!seins.length && !arbeitet && <div className={s.notiz}>{t('Noch nichts passiert.')}</div>}
        {seins.map((e) => (
          <NachrichtKarte key={e.id} e={e} leute={leute} mitSpur />
        ))}
        {arbeitet && runId && <LiveZug key={runId} runId={runId} person={p} />}
      </>
    )
  } else
    buehne = (
      <>
        <div className={s.otwrap}>
          <Karte k={baum} leute={leute} />
        </div>
        {ende && (
          <div className={s.ende}>
            <span className={s.lbl}>
              ✓ {t('ERGEBNIS VON')} {(leute[ende.von]?.name ?? ende.von).toUpperCase()}
            </span>
            <NachrichtKarte e={ende} leute={leute} />
          </div>
        )}
        <button type="button" className={s.alle} onClick={() => sichtWechseln('verlauf')}>
          ▸ {t('ganzer Verlauf — alle Nachrichten am Stück')}
        </button>
      </>
    )

  return (
    <div className={s.wrap}>
      <h2 className={s.h2}>
        🎫 {tk.titel}
        <span className={`${s.chip} ${z.art ? s[z.art] : ''}`}>{z.zeichen}</span>
      </h2>
      <Stand d={d} ende={verlauf[verlauf.length - 1]?.ts ?? 0} />
      {buehne}
      <Eskalation auftrag={tk} leute={leute} />
      <Einwurf id={id} offen={laeuftNoch} />
    </div>
  )
}
