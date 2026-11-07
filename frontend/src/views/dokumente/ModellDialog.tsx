import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useDokumenteAktionen, useModell, type ModellStand } from '@/api/dokumente'
import { Dialog } from '@/components/dialogs/Dialog'
import { useDialogs } from '@/stores/dialogs'
import s from './Dokumente.module.css'

function Formular({ st, onZu }: { st: ModellStand; onZu: () => void }) {
  const { t } = useTranslation()
  const act = useDokumenteAktionen()
  const [wahl, setWahl] = useState(st.modell)
  const [fehler, setFehler] = useState('')
  // Ein eingestelltes Modell, das es (nicht mehr) gibt, bleibt wählbar, damit
  // die Auswahl nicht still auf "aus" springt.
  const modelle =
    st.modell && !st.installiert.includes(st.modell)
      ? [st.modell, ...st.installiert]
      : st.installiert

  const speichern = async () => {
    setFehler('')
    try {
      await act.modellEinstellen.mutateAsync(wahl)
      onZu()
    } catch (e) {
      setFehler((e as Error).message)
    }
  }

  return (
    <div className={s.form}>
      <p className={s.erklaer}>
        {t(
          'Ein Sprachmodell auf diesem Rechner schreibt beim Einlesen den Titel (mit Betrag oder Jahr) und schlägt bei unbekannten Briefen Absender und Typ aus deinen vorhandenen Namen vor. Die Briefe verlassen dabei den Rechner nicht.',
        )}
      </p>
      <span className={s.leise}>
        {t(
          'Absender, Typ und Tags bekannter Briefe kommen weiter von den ähnlichsten einsortierten Dokumenten, das Datum aus dem Text. Gut geeignet ist qwen3.5:9b (6,6 GB), etwa 10 Sekunden pro Dokument.',
        )}
      </span>

      <div className={s.lbl}>🧠 {t('MODELL (OLLAMA)')}</div>
      {st.erreichbar ? (
        <select className={s.feld} value={wahl} onChange={(e) => setWahl(e.target.value)}>
          <option value="">{t('Aus (nur Regeln und ähnliche Dokumente)')}</option>
          {modelle.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      ) : (
        <div className={`${s.leise} ${s.warnText}`}>
          {st.ollama
            ? t('Ollama läuft gerade nicht. Beim nächsten Einlesen startet CONSTRUCT es selbst.')
            : t('Ollama ist nicht installiert.')}
          {st.modell && ` ${t('Eingestellt: {m}', { m: st.modell })}`}
        </div>
      )}
      {st.erreichbar && st.installiert.length === 0 && (
        <span className={s.leise}>{t('In Ollama ist noch kein Modell geladen.')}</span>
      )}

      {fehler && <div className={s.fehler}>{fehler}</div>}
      <div className={s.aktionen}>
        {st.erreichbar && (
          <button
            type="button"
            className={`${s.knopf} ${s.voll}`}
            disabled={act.modellEinstellen.isPending || wahl === st.modell}
            onClick={() => void speichern()}
          >
            {t('SPEICHERN')}
          </button>
        )}
        <button
          type="button"
          className={s.knopf}
          title={t('Ollama installieren, starten und Modelle laden')}
          onClick={() => (onZu(), useDialogs.getState().open('providers'))}
        >
          {t('OLLAMA VERWALTEN')}
        </button>
        <button type="button" className={`${s.knopf} ${s.gefahr}`} onClick={onZu}>
          {t('SCHLIESSEN')}
        </button>
      </div>
    </div>
  )
}

export function ModellDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const { data } = useModell(open)
  return (
    <Dialog open={open} onClose={onClose} title={t('Einsortieren mit lokalem Modell')}>
      {data ? (
        <Formular key={data.modell} st={data} onZu={onClose} />
      ) : (
        <div className={s.leise}>…</div>
      )}
    </Dialog>
  )
}
