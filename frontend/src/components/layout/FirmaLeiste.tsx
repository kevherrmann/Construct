import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { ungelesen, useAuftraege, useNotAus, useTeamAn, useTeamStand } from '@/api/team'
import { BREMSEN } from '@/lib/team'
import { useAuftraegeAnsicht } from '@/views/auftraege/store'
import { wartetAufNutzer } from '@/views/auftraege/zustand'
import s from './FirmaLeiste.module.css'

/** Zwei schmale Streifen über dem Hauptbereich, nur wenn etwas los ist:
 *
 *   Ruf         ein Auftrag wartet auf eine Entscheidung — die einzige Meldung, die
 *               nicht verpasst werden darf, deshalb bleibt sie, bis man reagiert hat;
 *   Aktivität   wer gerade arbeitet, plus der Not-Aus (nichts mehr zustellen).
 *
 *  Ein dauerhaft sichtbarer leerer Balken wäre nur Rahmen. */
export function FirmaLeiste() {
  const { t } = useTranslation()
  const an = useTeamAn()
  const navigate = useNavigate()
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
  const rufe = wartend.filter((x) => x.id !== auswahl)
  const ruf = rufe[0]
  const was = ruf
    ? ruf.einstellung
      ? t('wartet auf deine Wahl')
      : ruf.eskalation
        ? ruf.eskalation.bremse === 'eskaliert'
          ? t('hat eine Rückfrage an dich')
          : `${t('ist angehalten:')} ${t(BREMSEN[ruf.eskalation.bremse] ?? ruf.eskalation.bremse)}`
        : t('wartet auf dich')
    : ''
  // Fertige Aufträge, die man noch nicht gesehen hat — sonst fällt eine Lieferung
  // durch, während man woanders ist.
  const fertig = (liste ?? []).filter(
    (x) => x.status === 'fertig' && x.id !== auswahl && ungelesen(x) > 0,
  )
  const aktiv = stand?.aktiv ?? []
  const zeigenAktiv = aktiv.length > 0 || !!stand?.pausiert

  return (
    <>
      {ruf && (
        <button
          type="button"
          className={s.ruf}
          onClick={() => {
            oeffne(ruf.id)
            navigate('/auftraege')
          }}
        >
          <span>⏸</span>
          <span className={s.rt}>
            <b>{ruf.titel.length > 44 ? `${ruf.titel.slice(0, 44)}…` : ruf.titel}</b> — {was}
            {rufe.length > 1 && (
              <span className={s.leise}> ({t('und {n} weitere', { n: rufe.length - 1 })})</span>
            )}
          </span>
          <span className={s.rk}>{t('ANSEHEN')}</span>
        </button>
      )}
      {fertig.slice(0, 2).map((x) => (
        <button
          key={x.id}
          type="button"
          className={`${s.ruf} ${s.fertig}`}
          onClick={() => {
            oeffne(x.id)
            navigate('/auftraege')
          }}
        >
          <span>✓</span>
          <span className={s.rt}>
            <b>{x.titel.length > 44 ? `${x.titel.slice(0, 44)}…` : x.titel}</b> — {t('ist fertig')}
          </span>
          <span className={s.rk}>{t('ANSEHEN')}</span>
        </button>
      ))}
      {zeigenAktiv && (
        <div className={s.aktiv}>
          {aktiv.map((a) => (
            <span key={`${a.agent}:${a.ticket}`} style={{ ['--accent-rgb' as string]: a.color }}>
              <span className={s.punkt}>●</span>
              {a.name} {t('arbeitet')}
              {a.titel ? ` ${t('an')} „${a.titel.slice(0, 34)}“` : ''}{' '}
              <span className={s.leise}>{a.seit}s</span>
            </span>
          ))}
          <span className={s.pz}>
            {stand?.pausiert && <span className={s.angehalten}>{t('ANGEHALTEN')}</span>}
            <button
              type="button"
              className={stand?.pausiert ? s.an : ''}
              disabled={notAus.isPending}
              onClick={() => notAus.mutate(!stand?.pausiert)}
            >
              {stand?.pausiert ? `▶ ${t('WEITER')}` : `⏸ ${t('ALLES ANHALTEN')}`}
            </button>
          </span>
        </div>
      )}
    </>
  )
}
