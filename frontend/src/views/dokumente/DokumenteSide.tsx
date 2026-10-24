import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useDokumenteAktionen,
  useNamen,
  useSicherung,
  useUebersicht,
  type Filter,
} from '@/api/dokumente'
import { useUi } from '@/stores/ui'
import { zeitpunkt } from './format'
import { useDokumenteAnsicht } from './store'
import s from './Dokumente.module.css'

type Liste = 'absender' | 'typen' | 'tags'
const FELD: Record<Liste, keyof Filter> = { absender: 'absender', typen: 'typ', tags: 'tag' }

// Seitenleiste: Scannen/Hochladen, Eingang, Alle, Jahre, dann Absender, Typen, Tags.
export function DokumenteSide() {
  const { t } = useTranslation()
  const { data: u } = useUebersicht()
  const { filter, bereich, setScannen, setSicherung } = useDokumenteAnsicht()
  const sich = useSicherung().data
  const zu = useUi((st) => st.setSideOpen)
  const act = useDokumenteAktionen()
  const datei = useRef<HTMLInputElement>(null)
  const [auf, setAuf] = useState<Liste | null>('absender')
  const absender = useNamen('absender').data ?? []
  const typen = useNamen('typen').data ?? []
  const tags = useNamen('tags').data ?? []

  const wahl = (f: Partial<Filter>) => (bereich(f), zu(false))
  const nurDas = (f: Partial<Filter>) =>
    !filter.jahr &&
    filter.absender === (f.absender ?? null) &&
    filter.typ === (f.typ ?? null) &&
    filter.tag === (f.tag ?? null) &&
    filter.eingang === (f.eingang ?? null)

  const hoch = async (files: FileList | null) => {
    for (const f of Array.from(files ?? [])) await act.hochladen.mutateAsync(f)
    bereich({ eingang: true })
  }

  const gruppe = (k: Liste, titel: string, liste: { id: number; name: string; anzahl: number }[]) =>
    liste.length > 0 && (
      <>
        <button type="button" className={s.gruppe} onClick={() => setAuf(auf === k ? null : k)}>
          {auf === k ? '▾' : '▸'} {titel}
        </button>
        {auf === k &&
          liste.map((n) => {
            const an = filter[FELD[k]] === n.id
            return (
              <button
                key={n.id}
                type="button"
                className={`${s.punkt} ${s.klein} ${an ? s.sel : ''}`}
                onClick={() => wahl(an ? {} : { [FELD[k]]: n.id })}
              >
                <span className={s.name}>{n.name}</span>
                <span className={s.zahl}>{n.anzahl}</span>
              </button>
            )
          })}
      </>
    )

  return (
    <div>
      <div className={s.knoepfe}>
        <button
          type="button"
          className={s.add}
          disabled={u && !u.scanner}
          title={u && !u.scanner ? t('scanimage (SANE) ist nicht installiert') : undefined}
          onClick={() => (setScannen(true), zu(false))}
        >
          🖨 {t('SCANNEN')}
        </button>
        <button type="button" className={s.add} onClick={() => datei.current?.click()}>
          ＋ {t('HOCHLADEN')}
        </button>
        <input
          ref={datei}
          type="file"
          hidden
          multiple
          accept=".pdf,image/*,.heic"
          onChange={(e) => {
            void hoch(e.target.files)
            e.target.value = ''
          }}
        />
      </div>
      <button
        type="button"
        className={`${s.punkt} ${nurDas({ eingang: true }) ? s.sel : ''}`}
        onClick={() => wahl({ eingang: true })}
      >
        <span className={s.name}>📥 {t('Eingang')}</span>
        <span className={`${s.zahl} ${u?.eingang ? s.hell : ''}`}>{u?.eingang || ''}</span>
      </button>
      <button
        type="button"
        className={`${s.punkt} ${nurDas({}) ? s.sel : ''}`}
        onClick={() => wahl({})}
      >
        <span className={s.name}>🗂 {t('Alle Dokumente')}</span>
        <span className={s.zahl}>{u?.gesamt ?? ''}</span>
      </button>
      {(u?.jahre.length ?? 0) > 0 && <div className={s.trenner}>{t('JAHRE')}</div>}
      <div className={s.jahre}>
        {u?.jahre.map((j) => (
          <button
            key={j.jahr}
            type="button"
            className={`${s.pille} ${filter.jahr === j.jahr ? s.an : ''}`}
            onClick={() => wahl(filter.jahr === j.jahr ? {} : { jahr: j.jahr })}
            title={t('{n} Dokumente', { n: j.anzahl })}
          >
            {j.jahr}
          </button>
        ))}
      </div>
      {gruppe('absender', t('Absender'), absender)}
      {gruppe('typen', t('Typen'), typen)}
      {gruppe('tags', t('Tags'), tags)}
      {sich && u && u.gesamt > 0 && (
        <button
          type="button"
          className={`${s.sicherung} ${
            !sich.eingerichtet || Object.values(sich.ziele).some((z) => z.an && z.fehler)
              ? s.warnText
              : ''
          }`}
          onClick={() => (setSicherung(true), zu(false))}
        >
          {!sich.eingerichtet
            ? `⚠ ${t('Keine Sicherung eingerichtet')}`
            : Object.values(sich.ziele).some((z) => z.an && z.fehler)
              ? `⚠ ${t('Sicherung fehlgeschlagen')}`
              : `🛟 ${t('Gesichert')}: ${
                  zeitpunkt(
                    [sich.ziele.ordner.letzte, sich.ziele.server.letzte]
                      .filter(Boolean)
                      .sort()
                      .pop() ?? '',
                  ) || t('noch nicht')
                }`}
        </button>
      )}
      {u && u.lesen > 0 && (
        <div className={s.stand}>⏳ {t('{n} werden gerade gelesen', { n: u.lesen })}</div>
      )}
    </div>
  )
}
