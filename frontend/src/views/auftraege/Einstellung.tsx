import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuftragActions, type Auftrag, type Kandidat } from '@/api/team'
import { EFFORTS, MODELLE } from '@/lib/team'
import s from './Auftraege.module.css'

const RUNDEN_MAX = 2
const PREISE: Record<string, [number, number]> = {
  fable: [10, 50],
  opus: [5, 25],
  sonnet: [2, 10],
  haiku: [1, 5],
}
const FAKTOR: Record<string, number> = { low: 0.5, medium: 0.8, high: 1, xhigh: 1.5, max: 2.5 }

/** Grober Anhalt: ~15k Eingabe + ~1,5k Ausgabe je Zug, mit dem Effort skaliert. */
const kostenHinweis = (model: string, effort: string) => {
  const p = PREISE[model] ?? PREISE.sonnet!
  const zug = (15 * p[0]) / 1000 + ((1.5 * p[1]) / 1000) * (FAKTOR[effort] ?? 1)
  return `≈ ${zug.toFixed(2)} $`
}

const FARBEN = ['77,184,255', '255,182,72', '126,231,135']

/** Ein Vorschlag. Der Name steht oben und ist sofort änderbar — nicht hinter
 *  „Charakter ansehen“ versteckt; das war das eigentliche Interesse an der Auswahl. */
function Karte({
  k,
  i,
  beschaeftigt,
  onNimm,
}: {
  k: Kandidat
  i: number
  beschaeftigt: boolean
  onNimm: (k: Kandidat) => void
}) {
  const { t } = useTranslation()
  const [x, setX] = useState<Kandidat>(k)
  return (
    <div className={s.kand} style={{ ['--accent-rgb' as string]: FARBEN[i % 3] }}>
      <div className={s.kandname}>
        <input
          value={x.name}
          title={t('Name — gefällt er dir nicht, überschreib ihn')}
          onChange={(e) => setX({ ...x, name: e.target.value })}
        />
        <span className={s.leise}>{t('Name änderbar')}</span>
      </div>
      <div className={s.kt}>{x.titel}</div>
      <div className={s.kk}>{x.kurz}</div>
      <ul>
        {x.staerken.map((st) => (
          <li key={st}>{st}</li>
        ))}
      </ul>
      <div className={`${s.kk} ${s.kursiv}`}>{x.arbeitsweise}</div>
      <div className={s.kausst}>
        <b>{x.model}</b> / {x.effort} · <span>{kostenHinweis(x.model, x.effort)}</span>{' '}
        {t('pro Zug')}
        <br />
        <span className={s.leise}>{x.model_grund}</span>
        <br />
        {t('Werkzeuge:')} {x.allowed_tools.join(', ') || '—'}
        {x.can_delegate ? ` · ${t('darf verteilen')}` : ''}
      </div>
      <details>
        <summary>{t('Charakter ansehen und ändern')}</summary>
        <label>
          {t('Kürzel (so rufen die Kollegen)')}
          <input value={x.slug} onChange={(e) => setX({ ...x, slug: e.target.value })} />
        </label>
        <label>
          {t('Modell')}
          <select
            value={x.model}
            onChange={(e) => setX({ ...x, model: e.target.value as Kandidat['model'] })}
          >
            {Object.entries(MODELLE).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('Effort')}
          <select
            value={x.effort}
            onChange={(e) => setX({ ...x, effort: e.target.value as Kandidat['effort'] })}
          >
            {EFFORTS.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          {t('Charakter (SOUL.md)')}
          <textarea
            value={x.systemprompt}
            onChange={(e) => setX({ ...x, systemprompt: e.target.value })}
          />
        </label>
      </details>
      <button type="button" className={s.knopf} disabled={beschaeftigt} onClick={() => onNimm(x)}>
        {t('EINSTELLEN')}
      </button>
    </div>
  )
}

/** Das Einstellungsverfahren: fehlt eine Rolle, schlägt die Geschäftsführung EINEN
 *  Kandidaten vor, und der Nutzer stellt ein, benennt um oder fordert einen anderen
 *  an. Modell, Effort und die geschätzten Kosten stehen sichtbar auf der Karte. */
export function Einstellung({ auftrag }: { auftrag: Auftrag }) {
  const { t } = useTranslation()
  const act = useAuftragActions(auftrag.id)
  const [hinweis, setHinweis] = useState('')
  const [fehler, setFehler] = useState('')
  const e = auftrag.einstellung
  if (!e) return null
  const holen = (h: string) => {
    setFehler('')
    act.kandidaten.mutate(h, { onError: (x) => setFehler(x.message) })
  }
  const keiner = () => {
    if (
      confirm(
        t(
          'Niemanden einstellen? Die Firma muss den Auftrag dann mit den vorhandenen Leuten erledigen.',
        ),
      )
    )
      act.keiner.mutate(hinweis, { onError: (x) => setFehler(x.message) })
  }
  const beschaeftigt = act.kandidaten.isPending || act.einstellen.isPending

  if (!e.kandidaten.length)
    return (
      <div className={`${s.eskal} ${s.einst}`}>
        <h4>
          👥 {t('Es fehlt jemand für:')} {e.rolle}
        </h4>
        <div>{e.warum}</div>
        {act.kandidaten.isPending && (
          <div className={s.notiz}>⟲ {t('Die Suche läuft … (dauert ~20 s)')}</div>
        )}
        <div className={s.btns}>
          <button
            type="button"
            className={s.knopf}
            disabled={beschaeftigt}
            onClick={() => holen('')}
          >
            {t('VORSCHLAG HOLEN')}
          </button>
          <button type="button" className={s.knopf} onClick={keiner}>
            {t('Niemanden einstellen')}
          </button>
          <span className={s.msg}>{fehler && `⚠ ${fehler}`}</span>
        </div>
      </div>
    )
  return (
    <div className={`${s.eskal} ${s.einst}`}>
      <h4>
        👥 {t('Vorschlag für die Stelle')} „{e.rolle}“
      </h4>
      <div className={s.leise}>
        {e.warum} — {t('Name, Kürzel und alles andere kannst du ändern, bevor du einstellst.')}
      </div>
      <div className={s.kandidaten}>
        {e.kandidaten.map((k, i) => (
          <Karte
            key={`${e.runden}:${i}`}
            k={k}
            i={i}
            beschaeftigt={beschaeftigt}
            onNimm={(x) => act.einstellen.mutate(x, { onError: (err) => setFehler(err.message) })}
          />
        ))}
      </div>
      <div className={s.btns}>
        {e.runden < RUNDEN_MAX ? (
          <button
            type="button"
            className={s.knopf}
            disabled={beschaeftigt}
            onClick={() => holen(hinweis)}
          >
            {t('anderen Vorschlag')}
          </button>
        ) : (
          <span className={s.leise}>
            {t(
              'Keine weiteren Nachschläge — sonst wäre das die Endlosschleife, gegen die der Rest gebaut ist.',
            )}
          </span>
        )}
        <input
          className={s.feld}
          style={{ flex: 1, minWidth: 200 }}
          value={hinweis}
          placeholder={t('was dir nicht passt (optional)')}
          onChange={(x) => setHinweis(x.target.value)}
        />
        <button type="button" className={s.knopf} onClick={keiner}>
          {t('Niemanden einstellen')}
        </button>
        <span className={s.msg}>{fehler && `⚠ ${fehler}`}</span>
      </div>
    </div>
  )
}
