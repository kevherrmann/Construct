import { useEffect, useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useDokumente,
  useDokumenteAktionen,
  useNamen,
  useUebersicht,
  vorschauUrl,
  type Dok,
} from '@/api/dokumente'
import { DokumentDetail } from './DokumentDetail'
import { ScanDialog } from './ScanDialog'
import { datum } from './format'
import { useDokumenteAnsicht } from './store'
import s from './Dokumente.module.css'

function Zeile({ d, onOpen }: { d: Dok; onOpen: () => void }) {
  const { t } = useTranslation()
  const [bild, setBild] = useState(true)
  return (
    <button type="button" className={s.eintrag} onClick={onOpen}>
      <span className={s.mini}>
        {bild && d.zustand !== 'lesen' ? (
          <img src={vorschauUrl(d)} alt="" loading="lazy" onError={() => setBild(false)} />
        ) : (
          <span>{d.zustand === 'lesen' ? '⏳' : '📄'}</span>
        )}
      </span>
      <span className={s.edatum}>{datum(d.datum) || '—'}</span>
      <span className={s.etitel}>
        {d.titel || <i className={s.leise}>{t('ohne Titel')}</i>}
        <span className={s.unter}>
          {[d.absender, d.typ].filter(Boolean).join(' · ')}
          {d.tags.map((g) => (
            <span key={g.id} className={s.tag}>
              {g.name}
            </span>
          ))}
        </span>
      </span>
      <span className={`${s.schild} ${d.zustand === 'fehler' ? s.warn : d.eingang ? s.neu : ''}`}>
        {d.zustand === 'lesen'
          ? t('wird gelesen')
          : d.zustand === 'fehler'
            ? t('Fehler')
            : d.eingang
              ? t('Eingang')
              : `${d.seiten} S.`}
      </span>
    </button>
  )
}

// Hauptbereich: Suche und Liste, oder das geöffnete Dokument.
export function DokumenteMain() {
  const { t } = useTranslation()
  const { filter, setFilter, bereich, offen, oeffne, scannen, setScannen } = useDokumenteAnsicht()
  const { data: u } = useUebersicht()
  const { data, isPending } = useDokumente(filter)
  const absender = useNamen('absender').data ?? []
  const typen = useNamen('typen').data ?? []
  const tags = useNamen('tags').data ?? []
  const act = useDokumenteAktionen()
  const [q, setQ] = useState(filter.q)
  const [ueber, setUeber] = useState(false)
  const [fehler, setFehler] = useState('')

  // Erst suchen, wenn das Tippen kurz ruht
  useEffect(() => {
    const h = setTimeout(() => setFilter({ q }), 250)
    return () => clearTimeout(h)
  }, [q, setFilter])

  const liste = data?.dokumente ?? []
  const name = (l: { id: number; name: string }[], id: number | null) =>
    l.find((x) => x.id === id)?.name ?? ''
  const aktiv: { label: string; weg: () => void }[] = [
    filter.eingang && { label: t('Eingang'), weg: () => setFilter({ eingang: null }) },
    filter.jahr && { label: filter.jahr, weg: () => setFilter({ jahr: '' }) },
    filter.absender && {
      label: name(absender, filter.absender),
      weg: () => setFilter({ absender: null }),
    },
    filter.typ && { label: name(typen, filter.typ), weg: () => setFilter({ typ: null }) },
    filter.tag && { label: name(tags, filter.tag), weg: () => setFilter({ tag: null }) },
  ].filter(Boolean) as { label: string; weg: () => void }[]

  const hoch = async (files: FileList) => {
    setFehler('')
    for (const f of Array.from(files)) {
      try {
        await act.hochladen.mutateAsync(f)
      } catch (e) {
        setFehler(`${f.name}: ${(e as Error).message}`)
      }
    }
    bereich({ eingang: true })
  }
  const drop = (e: DragEvent) => {
    e.preventDefault()
    setUeber(false)
    void hoch(e.dataTransfer.files)
  }

  return (
    <div
      className={`${s.wrap} ${ueber ? s.ablage : ''}`}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        setUeber(true)
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setUeber(false)
      }}
      onDrop={drop}
    >
      {u && !u.texterkennung && (
        <div className={s.hinweis}>
          {t(
            'Texterkennung fehlt: Dokumente werden abgelegt, aber ihr Inhalt ist nicht durchsuchbar. Installiere OCRmyPDF mit deutschem Sprachpaket (Linux z. B. „ocrmypdf tesseract-langpack-deu“) und starte CONSTRUCT neu.',
          )}
        </div>
      )}
      {offen !== null ? (
        <DokumentDetail
          key={offen}
          id={offen}
          reihe={liste.map((d) => d.id)}
          onWeiter={(id) => oeffne(id)}
          onZu={() => oeffne(null)}
        />
      ) : (
        <>
          <div className={s.suche}>
            <input
              className={s.feld}
              placeholder={t('Suchen: Wörter aus Titel, Absender oder Inhalt …')}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          {aktiv.length > 0 && (
            <div className={s.pillen}>
              {aktiv.map((a) => (
                <button
                  key={a.label}
                  type="button"
                  className={`${s.pille} ${s.an}`}
                  onClick={a.weg}
                >
                  {a.label} ✕
                </button>
              ))}
            </div>
          )}
          {fehler && <div className={s.fehler}>{fehler}</div>}
          <div className={s.leise}>{data ? t('{n} Dokumente', { n: data.gesamt }) : ''}</div>
          {!isPending && liste.length === 0 && (
            <div className={s.leer}>
              {filter.eingang
                ? t(
                    'Eingang ist leer. Scanne etwas, lade PDFs oder Fotos hoch oder zieh sie hierher.',
                  )
                : t('Nichts gefunden.')}
            </div>
          )}
          <div className={s.liste}>
            {liste.map((d) => (
              <Zeile key={d.id} d={d} onOpen={() => oeffne(d.id)} />
            ))}
          </div>
        </>
      )}
      <ScanDialog open={scannen} onClose={() => setScannen(false)} />
    </div>
  )
}
