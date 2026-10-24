import { useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  dateiUrl,
  useDokument,
  useDokumenteAktionen,
  useNamen,
  type Aenderung,
  type Dok,
} from '@/api/dokumente'
import { tagsDazu } from './format'
import s from './Dokumente.module.css'

interface Props {
  id: number
  /** Ids der Liste, aus der das Dokument geöffnet wurde (für „weiter“). */
  reihe: number[]
  onWeiter: (id: number) => void
  onZu: () => void
}

function Formular({ d, reihe, onWeiter, onZu }: Omit<Props, 'id'> & { d: Dok }) {
  const { t } = useTranslation()
  const act = useDokumenteAktionen()
  const absender = useNamen('absender').data ?? []
  const typen = useNamen('typen').data ?? []
  const alleTags = useNamen('tags').data ?? []
  const [f, setF] = useState({
    titel: d.titel,
    datum: d.datum ?? '',
    absender: d.absender ?? '',
    typ: d.typ ?? '',
    notiz: d.notiz,
  })
  const [tags, setTags] = useState(d.tags.map((x) => x.name))
  const [tagEingabe, setTagEingabe] = useState('')
  const [fehler, setFehler] = useState('')
  const [text, setText] = useState(false)
  const [teilen, setTeilen] = useState<string | null>(null)

  const i = reihe.indexOf(d.id)
  const naechstes = i >= 0 ? (reihe[i + 1] ?? reihe[i - 1]) : undefined

  const daten = (): Aenderung => ({
    titel: f.titel,
    datum: f.datum || null,
    absender: f.absender.trim() || null,
    typ: f.typ.trim() || null,
    notiz: f.notiz,
    tags: tagsDazu(tags, tagEingabe),
  })
  const tu = async (v: Aenderung, dann: () => void) => {
    setFehler('')
    try {
      await act.aendern.mutateAsync({ id: d.id, ...v })
      dann()
    } catch (e) {
      setFehler((e as Error).message)
    }
  }
  // Bestätigen = aus dem Eingang nehmen. Im Eingang geht es gleich mit dem nächsten weiter.
  const bestaetigen = () =>
    void tu({ ...daten(), eingang: false }, () =>
      d.eingang && naechstes !== undefined ? onWeiter(naechstes) : onZu(),
    )
  const tagTaste = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      setTags(tagsDazu(tags, tagEingabe))
      setTagEingabe('')
    } else if (e.key === 'Backspace' && !tagEingabe && tags.length) {
      setTags(tags.slice(0, -1))
    }
  }
  const feld = (k: 'titel' | 'absender' | 'typ', label: string, liste?: string) => (
    <label className={s.feldbox}>
      <span className={s.lbl}>{label}</span>
      <input
        className={s.feld}
        list={liste}
        value={f[k]}
        onChange={(e) => setF({ ...f, [k]: e.target.value })}
      />
    </label>
  )

  return (
    <div className={s.form}>
      {d.zustand === 'lesen' && <div className={s.leise}>⏳ {t('Wird gerade gelesen …')}</div>}
      {d.hinweis && <div className={s.leise}>⚠ {d.hinweis}</div>}
      {feld('titel', t('TITEL'))}
      <div className={s.raster}>
        <label className={s.feldbox}>
          <span className={s.lbl}>{t('DATUM')}</span>
          <input
            type="date"
            className={s.feld}
            value={f.datum}
            onChange={(e) => setF({ ...f, datum: e.target.value })}
          />
        </label>
        {feld('absender', t('ABSENDER'), 'dok-absender')}
        {feld('typ', t('TYP'), 'dok-typen')}
      </div>
      <datalist id="dok-absender">
        {absender.map((n) => (
          <option key={n.id} value={n.name} />
        ))}
      </datalist>
      <datalist id="dok-typen">
        {typen.map((n) => (
          <option key={n.id} value={n.name} />
        ))}
      </datalist>
      <label className={s.feldbox}>
        <span className={s.lbl}>{t('TAGS')}</span>
        <span className={`${s.feld} ${s.tagfeld}`}>
          {tags.map((g) => (
            <button
              key={g}
              type="button"
              className={s.tag}
              title={t('entfernen')}
              onClick={() => setTags(tags.filter((x) => x !== g))}
            >
              {g} ✕
            </button>
          ))}
          <input
            list="dok-tags"
            value={tagEingabe}
            placeholder={tags.length ? '' : t('z. B. Steuer, Enter')}
            onChange={(e) => setTagEingabe(e.target.value)}
            onKeyDown={tagTaste}
          />
        </span>
        <datalist id="dok-tags">
          {alleTags
            .filter((n) => !tags.some((g) => g.toLowerCase() === n.name.toLowerCase()))
            .map((n) => (
              <option key={n.id} value={n.name} />
            ))}
        </datalist>
      </label>
      <label className={s.feldbox}>
        <span className={s.lbl}>{t('NOTIZ')}</span>
        <textarea
          className={s.text}
          value={f.notiz}
          onChange={(e) => setF({ ...f, notiz: e.target.value })}
        />
      </label>
      {fehler && <div className={s.fehler}>{fehler}</div>}
      <div className={s.aktionen}>
        <button type="button" className={`${s.knopf} ${s.voll}`} onClick={bestaetigen}>
          {d.eingang ? t('✓ BESTÄTIGEN') : t('SPEICHERN')}
        </button>
        {d.eingang ? (
          <button type="button" className={s.knopf} onClick={() => void tu(daten(), () => {})}>
            {t('NUR SPEICHERN')}
          </button>
        ) : (
          <button
            type="button"
            className={s.knopf}
            onClick={() => void tu({ ...daten(), eingang: true }, () => {})}
          >
            {t('ZURÜCK IN DEN EINGANG')}
          </button>
        )}
        <button
          type="button"
          className={`${s.knopf} ${s.gefahr}`}
          onClick={() => {
            if (!confirm(t('Dokument in den Papierkorb legen?'))) return
            void act.loeschen
              .mutateAsync(d.id)
              .then(() => (naechstes !== undefined ? onWeiter(naechstes) : onZu()))
          }}
        >
          {t('LÖSCHEN')}
        </button>
      </div>
      <div className={s.leise}>
        {t('Seiten: {n}', { n: d.seiten })} ·{' '}
        <a className={s.link} href={dateiUrl(d.id)} target="_blank" rel="noopener">
          {t('PDF öffnen')}
        </a>{' '}
        ·{' '}
        <button type="button" className={s.link} onClick={() => setText(!text)}>
          {text ? t('Text ausblenden') : t('gelesenen Text zeigen')}
        </button>
        {d.seiten > 1 && (
          <>
            {' '}
            ·{' '}
            <button
              type="button"
              className={s.link}
              onClick={() => setTeilen(teilen === null ? '' : null)}
            >
              {t('aufteilen')}
            </button>
          </>
        )}
      </div>
      {teilen !== null && (
        <div className={s.teilen}>
          <span className={s.leise}>
            {t('Mehrere Schreiben in einem Dokument? Seiten je Teil angeben, z. B. 1-2, 3, 4-6')}
          </span>
          <div className={s.aktionen}>
            <input
              className={s.feld}
              value={teilen}
              placeholder="1-2, 3, 4-6"
              onChange={(e) => setTeilen(e.target.value)}
            />
            <button
              type="button"
              className={s.knopf}
              onClick={() =>
                void (async () => {
                  setFehler('')
                  try {
                    const r = await act.teilen.mutateAsync({ id: d.id, seiten: teilen })
                    const erstes = r.dokumente[0]
                    if (erstes) onWeiter(erstes.id)
                    else onZu()
                  } catch (e) {
                    setFehler((e as Error).message)
                  }
                })()
              }
            >
              {t('AUFTEILEN')}
            </button>
          </div>
        </div>
      )}
      {text && <pre className={s.textblock}>{d.text || t('(kein Text erkannt)')}</pre>}
    </div>
  )
}

// Ein Dokument: links das PDF, rechts die Angaben.
export function DokumentDetail({ id, reihe, onWeiter, onZu }: Props) {
  const { t } = useTranslation()
  const { data: d, isError } = useDokument(id)
  const i = reihe.indexOf(id)
  return (
    <div>
      <div className={s.kopf}>
        <button type="button" className={s.zurueck} onClick={onZu}>
          ‹ {t('ZUR LISTE')}
        </button>
        {i >= 0 && reihe.length > 1 && (
          <span className={s.leise}>
            <button
              type="button"
              className={s.zurueck}
              disabled={i === 0}
              onClick={() => onWeiter(reihe[i - 1] ?? id)}
            >
              ‹
            </button>{' '}
            {i + 1} / {reihe.length}{' '}
            <button
              type="button"
              className={s.zurueck}
              disabled={i === reihe.length - 1}
              onClick={() => onWeiter(reihe[i + 1] ?? id)}
            >
              ›
            </button>
          </span>
        )}
      </div>
      {isError && <div className={s.leer}>{t('Das Dokument gibt es nicht mehr.')}</div>}
      {d && (
        <div className={s.detail}>
          <iframe
            className={s.pdf}
            src={dateiUrl(d.id)}
            title={d.titel || t('Dokument')}
            key={`${d.id}-${d.zustand}`}
          />
          <Formular
            // Neu aufsetzen, sobald das Lesen fertig ist: dann stehen die Vorschläge drin
            key={`${d.id}-${d.zustand}`}
            d={d}
            reihe={reihe}
            onWeiter={onWeiter}
            onZu={onZu}
          />
        </div>
      )}
    </div>
  )
}
