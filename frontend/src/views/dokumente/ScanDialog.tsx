import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  scanSeiteUrl,
  useDokumenteAktionen,
  useScanGeraete,
  useScanStand,
  type ScanStand,
} from '@/api/dokumente'
import { Dialog } from '@/components/dialogs/Dialog'
import { useDokumenteAnsicht } from './store'
import s from './Dokumente.module.css'

interface SeitenProps {
  st: ScanStand
  /** Nur gesetzt, wenn Rückseiten von Hand ihrem Blatt zugeordnet werden müssen. */
  zuordnung?: number[]
  setZuordnung?: (z: number[]) => void
}

function Seiten({ st, zuordnung, setZuordnung }: SeitenProps) {
  const { t } = useTranslation()
  const n = Math.max(st.vorne, st.hinten)
  if (!n) return null
  return (
    <div className={s.seiten}>
      {Array.from({ length: st.vorne }, (_, i) => (
        <figure key={`v${i}`} className={s.seite}>
          <img src={`${scanSeiteUrl(st.id, 'vorne', i + 1)}?${st.vorne}`} alt="" />
          <figcaption>{i + 1}</figcaption>
        </figure>
      ))}
      {st.hinten > 0 &&
        Array.from({ length: st.hinten }, (_, i) => (
          <figure key={`h${i}`} className={`${s.seite} ${s.rueck}`}>
            <img src={`${scanSeiteUrl(st.id, 'hinten', i + 1)}?${st.hinten}`} alt="" />
            {zuordnung && setZuordnung ? (
              <select
                className={s.wahl}
                value={zuordnung[i] ?? 0}
                aria-label={t('Rückseite von Blatt')}
                onChange={(e) => {
                  const z = [...zuordnung]
                  z[i] = Number(e.target.value)
                  setZuordnung(z)
                }}
              >
                <option value={0}>{t('zu Blatt …')}</option>
                {Array.from({ length: st.vorne }, (_, b) => (
                  <option key={b} value={b + 1}>
                    {t('hinter {n}', { n: b + 1 })}
                  </option>
                ))}
              </select>
            ) : (
              <figcaption>R{i + 1}</figcaption>
            )}
          </figure>
        ))}
    </div>
  )
}

// Scannen in Schritten: Stapel oder Glas, auf Wunsch Rückseiten, dann einzeln oder zusammen.
export function ScanDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const act = useDokumenteAktionen()
  const bereich = useDokumenteAnsicht((x) => x.bereich)
  const geraete = useScanGeraete(open)
  const [sid, setSid] = useState<string | null>(null)
  const [farbe, setFarbe] = useState(false)
  const [fehler, setFehler] = useState('')
  const { data: st } = useScanStand(sid)
  const [zuordnung, setZuordnung] = useState<number[]>([])

  const tu = async (fn: () => Promise<unknown>) => {
    setFehler('')
    try {
      await fn()
    } catch (e) {
      setFehler((e as Error).message)
    }
  }
  const start = (quelle: 'auto' | 'einzug' | 'glas') =>
    tu(async () => setSid((await act.scanStart.mutateAsync({ quelle, farbe })).id))
  const weiter = (was: 'glas' | 'einzug' | 'rueckseiten') =>
    tu(() => act.scanWeiter.mutateAsync({ sid: sid!, was }))
  const schliessen = () => {
    if (sid && st?.zustand !== 'fertig') void act.scanAbbrechen.mutateAsync(sid)
    setSid(null)
    setZuordnung([])
    setFehler('')
    onClose()
  }
  // Wurden nur einzelne Blätter gewendet, lässt sich nicht abzählen, welche
  // Rückseite wohin gehört: dann ordnet der Nutzer sie an den Vorschaubildern zu.
  const vonHand = !!st && st.hinten > 0 && st.hinten !== st.vorne
  const fertig = (einzeln: boolean) =>
    tu(async () => {
      await act.scanFertig.mutateAsync({
        sid: sid!,
        einzeln,
        zuordnung: vonHand
          ? Array.from({ length: st.hinten }, (_, i) => zuordnung[i] ?? 0)
          : undefined,
      })
      setSid(null)
      setZuordnung([])
      bereich({ eingang: true })
      onClose()
    })

  const blaetter = st?.vorne ?? 0
  const laeuft = st?.zustand === 'scannt'

  return (
    <Dialog open={open} onClose={schliessen} title={t('Scannen')} wide>
      {!sid && (
        <div className={s.form}>
          <div className={s.leise}>
            {geraete.isPending
              ? t('Suche Scanner …')
              : geraete.data?.geraete[0]
                ? `🖨 ${geraete.data.geraete[0].name}`
                : t('Kein Scanner gefunden. Ist er eingeschaltet und im selben Netz?')}
          </div>
          <p className={s.erklaer}>
            {t(
              'Liegt Papier im Einzug, wird der ganze Stapel gescannt, sonst eine Seite vom Glas. Beidseitig bedruckt: erst die Vorderseiten, danach den Stapel wenden und die Rückseiten. Leere Rückseiten fallen von selbst weg.',
            )}
          </p>
          <label className={s.leise}>
            <input type="checkbox" checked={farbe} onChange={(e) => setFarbe(e.target.checked)} />{' '}
            {t('In Farbe (sonst Graustufen, reicht für Briefe)')}
          </label>
          <div className={s.aktionen}>
            <button
              type="button"
              className={`${s.knopf} ${s.voll}`}
              disabled={!geraete.data?.geraete.length}
              onClick={() => void start('auto')}
            >
              {t('SCANNEN')}
            </button>
            <button
              type="button"
              className={s.knopf}
              disabled={!geraete.data?.geraete.length}
              onClick={() => void start('glas')}
            >
              {t('VOM GLAS')}
            </button>
          </div>
        </div>
      )}
      {sid && st && (
        <div className={s.form}>
          <div className={s.status}>
            {laeuft
              ? `⏳ ${st.seite === 'hinten' ? t('Scanne Rückseiten …') : t('Scanne …')} ${t('{n} Seiten', { n: st.seite === 'hinten' ? st.hinten : st.vorne })}`
              : st.zustand === 'stau'
                ? `⚠ ${t('Einzugsfehler. Die fertigen Seiten sind gesichert.')}`
                : st.zustand === 'fehler'
                  ? `⚠ ${st.meldung}`
                  : st.hinten
                    ? t('{v} Vorder- und {h} Rückseiten gescannt.', { v: st.vorne, h: st.hinten })
                    : t('{n} Seiten gescannt.', { n: st.vorne })}
          </div>
          <Seiten
            st={st}
            zuordnung={vonHand && !laeuft ? zuordnung : undefined}
            setZuordnung={setZuordnung}
          />
          {vonHand && !laeuft && (
            <p className={s.erklaer}>
              {t(
                'Es wurden nicht alle Blätter gewendet. Wähl unter jeder Rückseite, hinter welches Blatt sie gehört. Ohne Auswahl wird sie ein eigenes Dokument.',
              )}
            </p>
          )}
          {st.zustand === 'stau' && (
            <>
              <p className={s.erklaer}>
                {t(
                  'Stau beseitigen, die übrigen Blätter wieder einlegen (ab dem ersten, das fehlt) und weiterscannen.',
                )}
              </p>
              <div className={s.aktionen}>
                <button
                  type="button"
                  className={`${s.knopf} ${s.voll}`}
                  onClick={() => void weiter('einzug')}
                >
                  {t('WEITER SCANNEN')}
                </button>
              </div>
            </>
          )}
          {!laeuft &&
            st.zustand !== 'stau' &&
            st.quelle === 'einzug' &&
            st.hinten === 0 &&
            blaetter > 0 && (
              <p className={s.erklaer}>
                {t(
                  'Hinten auch bedruckt? Dann den ganzen Stapel so, wie er herausgekommen ist, umdrehen, auch die Blätter ohne Rückseite, wieder einlegen und „Rückseiten scannen“ drücken. Leere Rückseiten fallen von selbst weg.',
                )}
              </p>
            )}
          {!laeuft && (
            <div className={s.aktionen}>
              {st.quelle === 'einzug' &&
                st.hinten === 0 &&
                blaetter > 0 &&
                st.zustand !== 'stau' && (
                  <button
                    type="button"
                    className={s.knopf}
                    onClick={() => void weiter('rueckseiten')}
                  >
                    {t('RÜCKSEITEN SCANNEN')}
                  </button>
                )}
              {st.quelle === 'glas' && (
                <button type="button" className={s.knopf} onClick={() => void weiter('glas')}>
                  {t('NOCH EINE SEITE')}
                </button>
              )}
            </div>
          )}
          {!laeuft && blaetter > 0 && (
            <>
              <div className={s.lbl}>{t('FERTIG, UND DANN:')}</div>
              <div className={s.aktionen}>
                {blaetter > 1 && (
                  <button
                    type="button"
                    className={`${s.knopf} ${s.voll}`}
                    onClick={() => void fertig(true)}
                  >
                    {t('JEDES BLATT EINZELN')}
                  </button>
                )}
                <button
                  type="button"
                  className={`${s.knopf} ${blaetter > 1 ? '' : s.voll}`}
                  onClick={() => void fertig(false)}
                >
                  {blaetter > 1 ? t('ALLES EIN DOKUMENT') : t('ABLEGEN')}
                </button>
                <button type="button" className={`${s.knopf} ${s.gefahr}`} onClick={schliessen}>
                  {t('VERWERFEN')}
                </button>
              </div>
              {blaetter > 1 && (
                <p className={s.leise}>
                  {t(
                    'Einzeln: mehrere Briefe in einem Stapel. Ein Dokument: ein mehrseitiges Schreiben.',
                  )}
                </p>
              )}
            </>
          )}
        </div>
      )}
      {fehler && <div className={s.fehler}>{fehler}</div>}
    </Dialog>
  )
}
