import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useDokumenteAktionen,
  useSicherung,
  type ProbeErgebnis,
  type SicherungStand,
  type SicherungZiel,
} from '@/api/dokumente'
import { Dialog } from '@/components/dialogs/Dialog'
import { zeitpunkt } from './format'
import s from './Dokumente.module.css'

function Zustand({ z }: { z: SicherungZiel }) {
  const { t } = useTranslation()
  if (!z.an) return null
  return (
    <div className={`${s.leise} ${z.fehler ? s.warnText : ''}`}>
      {z.fehler
        ? `⚠ ${z.fehler}`
        : z.letzte
          ? `${z.aktuell ? '✓' : '…'} ${t('Zuletzt gesichert: {z}', { z: zeitpunkt(z.letzte) })}${z.ergebnis ? ` · ${z.ergebnis}` : ''}`
          : t('Noch nie gesichert.')}
    </div>
  )
}

function Formular({ st, onZu }: { st: SicherungStand; onZu: () => void }) {
  const { t } = useTranslation()
  const act = useDokumenteAktionen()
  const [ordner, setOrdner] = useState(st.ordner)
  const [srv, setSrv] = useState({
    host: st.server.host ?? '',
    benutzer: st.server.benutzer ?? '',
    port: st.server.port ? String(st.server.port) : '',
    ordner: st.server.ordner ?? '',
    schluessel: st.server.schluessel ?? '',
  })
  const [kennwort, setKennwort] = useState('')
  const [kennwort2, setKennwort2] = useState('')
  const [fehler, setFehler] = useState('')
  const [probe, setProbe] = useState<{ ziel: string; r: ProbeErgebnis } | null>(null)
  const [arbeitet, setArbeitet] = useState('')

  const tu = async (was: string, fn: () => Promise<unknown>) => {
    setFehler('')
    setArbeitet(was)
    try {
      await fn()
    } catch (e) {
      setFehler((e as Error).message)
    } finally {
      setArbeitet('')
    }
  }
  const speichern = () =>
    tu('speichern', async () => {
      if (kennwort && kennwort !== kennwort2)
        throw new Error(t('Die beiden Kennwörter sind verschieden.'))
      await act.sicherungEinrichten.mutateAsync({
        ordner,
        server: { ...srv, port: Number(srv.port) || 0 },
        ...(kennwort ? { kennwort } : {}),
      })
      setKennwort('')
      setKennwort2('')
    })
  const feld = (k: keyof typeof srv, label: string, platz = '') => (
    <label className={s.feldbox}>
      <span className={s.lbl}>{label}</span>
      <input
        className={s.feld}
        value={srv[k]}
        placeholder={platz}
        onChange={(e) => setSrv({ ...srv, [k]: e.target.value })}
      />
    </label>
  )

  return (
    <div className={s.form}>
      <p className={s.erklaer}>
        {t(
          'Bevor Papier in den Müll geht: Die Ablage liegt sonst nur auf dieser Platte. Am besten beide Ziele, eines im Haus und eines außer Haus. Gesichert wird von selbst, sobald sich etwas geändert hat.',
        )}
      </p>

      <div className={s.lbl}>📁 {t('ORDNER (EXTERNE PLATTE, USB, NAS)')}</div>
      <input
        className={s.feld}
        value={ordner}
        placeholder="/run/media/…/Sicherung"
        onChange={(e) => setOrdner(e.target.value)}
      />
      <span className={s.leise}>
        {t(
          'Unverschlüsselt und ohne CONSTRUCT lesbar. Der Ordner muss schon existieren: ist die Platte nicht eingesteckt, wird nichts gesichert und es kommt eine Warnung. Ein Cloud-Sync-Ordner (Dropbox, OneDrive) würde die Dokumente unverschlüsselt hochladen.',
        )}
      </span>
      <Zustand z={st.ziele.ordner} />

      <div className={s.lbl}>🌐 {t('SERVER PER SFTP (VERSCHLÜSSELT)')}</div>
      <div className={s.raster}>
        {feld('host', t('SERVER'), 'meinserver.de')}
        {feld('benutzer', t('BENUTZER'), t('aus ~/.ssh/config'))}
        {feld('port', t('PORT'), '22')}
        {feld('ordner', t('ORDNER AUF DEM SERVER'), 'sicherungen/dokumente')}
      </div>
      {feld('schluessel', t('SSH-SCHLÜSSEL (OPTIONAL)'), '~/.ssh/id_ed25519')}
      <span className={s.leise}>
        {t(
          'Eigener Server, Storage Box oder NAS mit SFTP. Anmeldung nur per SSH-Schlüssel. Auf dem Server liegen nur verschlüsselte Dateien.',
        )}
      </span>
      <div className={s.raster}>
        <label className={s.feldbox}>
          <span className={s.lbl}>
            {st.kennwort ? t('NEUES KENNWORT (LEER = BEHALTEN)') : t('KENNWORT ZUM VERSCHLÜSSELN')}
          </span>
          <input
            className={s.feld}
            type="password"
            autoComplete="new-password"
            value={kennwort}
            onChange={(e) => setKennwort(e.target.value)}
          />
        </label>
        <label className={s.feldbox}>
          <span className={s.lbl}>{t('KENNWORT WIEDERHOLEN')}</span>
          <input
            className={s.feld}
            type="password"
            autoComplete="new-password"
            value={kennwort2}
            onChange={(e) => setKennwort2(e.target.value)}
          />
        </label>
      </div>
      <span className={`${s.leise} ${s.warnText}`}>
        {t(
          'Kennwort aufschreiben und getrennt vom Rechner aufbewahren. Ohne es lässt sich die Server-Sicherung von niemandem mehr öffnen.',
        )}
      </span>
      <Zustand z={st.ziele.server} />

      {fehler && <div className={s.fehler}>{fehler}</div>}
      {probe && (
        <div className={probe.r.fehlt_anzahl ? s.fehler : s.gutText}>
          {probe.r.fehlt_anzahl || probe.r.dokumente !== probe.r.dokumente_soll
            ? t('Probe {ziel}: {n} Dateien fehlen oder weichen ab.', {
                ziel: probe.ziel,
                n: probe.r.fehlt_anzahl,
              })
            : t('Probe {ziel}: alle {n} Dateien und {d} Dokumente zurückgeholt und geprüft.', {
                ziel: probe.ziel,
                n: probe.r.dateien,
                d: probe.r.dokumente,
              })}
        </div>
      )}
      <div className={s.aktionen}>
        <button
          type="button"
          className={`${s.knopf} ${s.voll}`}
          disabled={!!arbeitet}
          onClick={() => void speichern()}
        >
          {arbeitet === 'speichern' ? '…' : t('SPEICHERN')}
        </button>
        <button
          type="button"
          className={s.knopf}
          disabled={!!arbeitet || !st.eingerichtet || st.laeuft}
          onClick={() => void tu('jetzt', () => act.sicherungJetzt.mutateAsync())}
        >
          {arbeitet === 'jetzt' || st.laeuft ? t('SICHERT …') : t('JETZT SICHERN')}
        </button>
        {(['ordner', 'server'] as const)
          .filter((z) => st.ziele[z].an && st.ziele[z].letzte)
          .map((z) => (
            <button
              key={z}
              type="button"
              className={s.knopf}
              disabled={!!arbeitet}
              title={t(
                'Holt die Sicherung in einen leeren Ordner zurück und vergleicht jede Datei.',
              )}
              onClick={() =>
                void tu(`probe-${z}`, async () =>
                  setProbe({ ziel: z, r: await act.sicherungPruefen.mutateAsync(z) }),
                )
              }
            >
              {arbeitet === `probe-${z}` ? '…' : t('PROBE {z}', { z: z.toUpperCase() })}
            </button>
          ))}
        <button type="button" className={`${s.knopf} ${s.gefahr}`} onClick={onZu}>
          {t('SCHLIESSEN')}
        </button>
      </div>
    </div>
  )
}

export function SicherungDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const { data } = useSicherung()
  return (
    <Dialog open={open} onClose={onClose} title={t('Sicherung')} wide>
      {data && <Formular st={data} onZu={onClose} />}
    </Dialog>
  )
}
