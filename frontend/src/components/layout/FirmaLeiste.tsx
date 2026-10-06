import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'
import { ungelesen, useAuftraege, useNotAus, useTeamAn, useTeamStand } from '@/api/team'
import { BREMSEN } from '@/lib/team'
import { useAuftraegeAnsicht } from '@/views/auftraege/store'
import { wartetAufNutzer } from '@/views/auftraege/zustand'
import s from './FirmaLeiste.module.css'

/** Auf höchstens n Zeichen, an der Wortgrenze, mit „…“ (der ganze Titel steht im title). */
const kurz = (text: string, n: number) =>
  text.length <= n
    ? text
    : `${text
        .slice(0, n)
        .replace(/\s+\S*$/, '')
        .replace(/[\s,.:;–-]+$/, '')}…`

/** Ein schmaler Streifen über dem Hauptbereich, nur wenn etwas los ist. Er zeigt
 *  die wichtigste Meldung, die anderen zählt er nur (alle stehen in den Aufträgen):
 *
 *   Ruf         ein Auftrag wartet auf eine Entscheidung — die einzige Meldung, die
 *               nicht verpasst werden darf, deshalb bleibt sie, bis man reagiert hat;
 *   Fertig      eine Lieferung, die man noch nicht gesehen hat;
 *   Aktivität   wer gerade arbeitet (bei einer Meldung nur als farbige Punkte),
 *               rechts immer der Not-Aus (nichts mehr zustellen).
 *
 *  Ein dauerhaft sichtbarer leerer Balken wäre nur Rahmen; zwei übereinander kosten
 *  auf dem Handy ein Viertel des Bildschirms. */
export function FirmaLeiste() {
  const { t } = useTranslation()
  const an = useTeamAn()
  const navigate = useNavigate()
  const imAuftragBereich = useLocation().pathname.startsWith('/auftraege')
  const { data: liste } = useAuftraege()
  const { data: stand } = useTeamStand()
  const notAus = useNotAus()
  const { auswahl, oeffne } = useAuftraegeAnsicht()

  const wartend = (liste ?? []).filter((x) => wartetAufNutzer(x.status))
  // Titel und Reiter zeigen es auch dann, wenn das Fenster nicht im Vordergrund ist.
  useEffect(() => {
    if (!an) return
    const alt = document.title.replace(/^\(\d+\) ⏸ /, '')
    document.title = wartend.length ? `(${wartend.length}) ⏸ ${alt}` : alt
    return () => {
      document.title = document.title.replace(/^\(\d+\) ⏸ /, '')
    }
  }, [an, wartend.length])

  if (!an) return null
  // Den gerade geöffneten Auftrag nicht anmahnen — man sieht ihn ja.
  // (nur dort sieht man ihn ja; in anderen Ansichten bleibt die Meldung stehen)
  const rufe = wartend.filter((x) => !(imAuftragBereich && x.id === auswahl))
  const ruf = rufe[0]
  const was = ruf
    ? ruf.eskalation
      ? ruf.eskalation.bremse === 'eskaliert'
        ? t('hat eine Rückfrage an dich')
        : `${t('ist angehalten:')} ${t(BREMSEN[ruf.eskalation.bremse] ?? ruf.eskalation.bremse)}`
      : t('wartet auf dich')
    : ''
  // Fertige Aufträge, die man noch nicht gesehen hat — sonst fällt eine Lieferung
  // durch, während man woanders ist.
  const fertig = (liste ?? []).filter(
    (x) => x.status === 'fertig' && !(imAuftragBereich && x.id === auswahl) && ungelesen(x) > 0,
  )
  const aktiv = stand?.aktiv ?? []
  const zeigenAktiv = aktiv.length > 0 || !!stand?.pausiert

  const fertigEins = fertig[0]
  const meldung = ruf ?? fertigEins
  if (!meldung && !zeigenAktiv) return null
  const weitere = ruf ? rufe.length - 1 + fertig.length : fertig.length - 1
  const titel = (x: { titel: string }) => kurz(x.titel, 60)
  const arbeitetAn = (a: (typeof aktiv)[number]) =>
    `${a.name} ${t('arbeitet')}${a.titel ? ` ${t('an „{t}“', { t: a.titel })}` : ''}`

  return (
    <div className={`${s.leiste} ${ruf ? s.ruf : fertigEins ? s.fertig : ''}`}>
      {meldung ? (
        <button
          type="button"
          className={s.meldung}
          onClick={() => {
            oeffne(meldung.id)
            navigate('/auftraege')
          }}
        >
          <span className={s.zeichen}>{ruf ? '!' : '✓'}</span>
          <span className={s.rt}>
            <b>{titel(meldung)}</b>
            <span className={s.was}>{ruf ? was : t('ist fertig')}</span>
          </span>
          {weitere > 0 && (
            <span className={s.mehr} title={t('und {n} weitere', { n: weitere })}>
              +{weitere}
            </span>
          )}
          <span className={s.rk}>{t('ANSEHEN')}</span>
        </button>
      ) : (
        <span className={`${s.wer} ${aktiv.length > 1 ? s.mehrere : ''}`}>
          {aktiv.map((a) => (
            <span
              key={`${a.agent}:${a.ticket}`}
              className={s.person}
              style={{ ['--accent-rgb' as string]: a.color }}
              title={arbeitetAn(a)}
            >
              <span className={s.punkt}>●</span>
              {a.name}
              <span className={s.verb}> {t('arbeitet')}</span>
              <span className={s.ziel}>
                {a.titel ? ` ${t('an „{t}“', { t: kurz(a.titel, 32) })}` : ''}{' '}
                <span className={s.leise}>{a.seit}s</span>
              </span>
            </span>
          ))}
          {aktiv.length > 1 && <span className={s.zusammen}>{t('arbeiten')}</span>}
        </span>
      )}
      {zeigenAktiv && (
        <span className={s.pz}>
          {meldung &&
            aktiv.map((a) => (
              <span
                key={`${a.agent}:${a.ticket}`}
                className={s.punkt}
                style={{ ['--accent-rgb' as string]: a.color }}
                title={arbeitetAn(a)}
                aria-label={arbeitetAn(a)}
                role="img"
              >
                ●<span className={s.name}>{a.name}</span>
              </span>
            ))}
          {stand?.pausiert && <span className={s.angehalten}>{t('ANGEHALTEN')}</span>}
          <button
            type="button"
            className={`${s.notaus} ${stand?.pausiert ? s.an : ''}`}
            disabled={notAus.isPending}
            onClick={() => notAus.mutate(!stand?.pausiert)}
            title={stand?.pausiert ? t('WEITER') : t('ALLES ANHALTEN')}
            aria-label={stand?.pausiert ? t('WEITER') : t('ALLES ANHALTEN')}
          >
            {stand?.pausiert ? '▶' : '⏸'}
            <span className={s.notausText}>
              {stand?.pausiert ? t('WEITER') : t('ALLES ANHALTEN')}
            </span>
          </button>
        </span>
      )}
    </div>
  )
}
