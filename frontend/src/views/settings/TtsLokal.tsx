import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  installTtsLokal,
  probeAusGemini,
  probeHochladen,
  stopTtsLokal,
  useTtsLokal,
} from '@/api/settings'
import { say, stopSay } from '@/lib/audio'
import { rich } from '@/lib/rich'
import { trServer } from '@/lib/serverText'
import { useSettings } from '@/stores/settings'
import { LogBox, Note } from './parts'
import s from './Settings.module.css'

const zahl = (n: number | undefined) =>
  (n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 1 })

// Lokale Stimme (Chatterbox, server/tts_lokal.py). Aus, bis man sie hier
// ausdrücklich einschaltet: sie belegt beim Vorlesen Grafikspeicher und
// braucht einen großen Download. Darum steht die Warnung immer da, und das
// Einschalten fragt noch einmal nach.
export function TtsLokal() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const boot = useSettings((st) => st.boot)
  const tts = useSettings((st) => st.settings.tts)
  const save = useSettings((st) => st.save)
  const lang = boot.lang
  const an = tts.engine === 'lokal'
  const probe = tts.probe?.[lang] ?? ''
  const st = useTtsLokal()
  const d = st.data
  const [note, setNote] = useState('')
  const [probeNote, setProbeNote] = useState('')
  const datei = useRef<HTMLInputElement>(null)
  const spieler = useRef<HTMLAudioElement | null>(null)
  useEffect(() => () => spieler.current?.pause(), [])

  const laeuft = !!d?.install.running
  // Geklappt sieht man am Schild (INSTALLIERT); hier nur, was schiefging.
  const installFehler = d && !laeuft && d.install.error ? '⚠ ' + trServer(d.install.error) : ''

  const warnung = t(
    '⚠ Belegt beim Vorlesen rund {vram} GB Grafikspeicher (VRAM) und gibt ihn erst {n} Min nach dem letzten Vorlesen wieder frei. So lange fehlt er Spielen, Bonsai oder anderen lokalen KI-Modellen. Einmalig rund {dl} GB Download (Programm und Modell). Ohne NVIDIA-Grafikkarte rechnet der Prozessor, das ist deutlich langsamer.',
    { vram: zahl(d?.vram_gb ?? 4), n: d?.idle_min ?? 10, dl: d?.download_gb ?? 9 },
  )
  const gpu = d?.gpu?.name
    ? t('Grafikkarte: {name} · {total} GB, davon {free} GB frei', {
        name: d.gpu.name,
        total: zahl(d.gpu.total_gb),
        free: zahl(d.gpu.free_gb),
      })
    : d
      ? t('Keine NVIDIA-Grafikkarte erkannt.')
      : ''

  const umschalten = async (ein: boolean) => {
    if (ein) {
      if (!window.confirm(t('Lokale Stimme einschalten?') + '\n\n' + warnung)) return
      await save({ tts: { engine: 'lokal' } })
    } else {
      stopSay()
      await save({ tts: { engine: 'gemini' } })
      // Sofort freigeben, nicht erst nach dem Leerlauf.
      await stopTtsLokal().catch(() => undefined)
    }
    void st.refetch()
  }

  const installieren = async () => {
    setNote('')
    try {
      await installTtsLokal()
      void st.refetch()
    } catch (e) {
      setNote('⚠ ' + trServer((e as Error).message))
    }
  }

  const freigeben = async () => {
    stopSay()
    qc.setQueryData(['tts-lokal'], await stopTtsLokal())
  }

  const probeSetzen = async (holen: () => Promise<{ url: string }>, warte: string) => {
    setProbeNote(warte)
    try {
      const { url } = await holen()
      await save({ tts: { probe: { [lang]: url } } })
      setProbeNote(t('✓ gespeichert'))
    } catch (e) {
      setProbeNote('⚠ ' + trServer((e as Error).message))
    }
  }

  const probeAnhoeren = () => {
    stopSay()
    spieler.current?.pause()
    spieler.current = new Audio(probe)
    void spieler.current.play()
  }

  const hoerprobe = async () => {
    spieler.current?.pause()
    setProbeNote(d?.laeuft ? '…' : t('… lädt das Modell (ca. 15 s)'))
    try {
      await say(
        t('Hallo {u}, ich bin {a}. So klinge ich mit dieser Stimme.', {
          u: boot.user || t('Du'),
          a: boot.assistant,
        }),
        { owner: 'settings-preview-lokal' },
      )
      setProbeNote('')
    } catch (e) {
      stopSay()
      setProbeNote('⚠ ' + trServer((e as Error).message))
    }
    void st.refetch()
  }

  return (
    <>
      <div className={s.row}>
        <label>
          <input type="checkbox" checked={an} onChange={(e) => void umschalten(e.target.checked)} />
          <span>
            <span className={s.t}>{t('Lokale Stimme (Chatterbox)')}</span>
            <span className={s.d}>
              {rich(
                t(
                  'Liest auf <b>deinem Rechner</b> vor statt über Gemini: kein Kontingent, keine Kosten, kein Text verlässt den Rechner. Ahmt eine Stimmprobe nach, etwa deine Gemini-Stimme.',
                ),
              )}
            </span>
            <span className={s.warnung}>{warnung}</span>
            {gpu && <span className={s.d}>{gpu}</span>}
          </span>
        </label>
      </div>

      {an && d && (
        <div className={s.row}>
          <span className={s.grow}>
            <span className={s.head}>
              <span className={s.t}>{t('Lokales Modell')}</span>
              {d.installiert ? (
                <span className={`${s.tag} ${s.ok}`}>{t('INSTALLIERT')}</span>
              ) : (
                <span className={`${s.tag} ${s.warn}`}>{t('NICHT INSTALLIERT')}</span>
              )}
            </span>
            <span className={s.d}>
              {!d.installiert
                ? t(
                    'Chatterbox Multilingual V3 von Resemble AI (MIT-Lizenz), läuft in einer eigenen Python-Umgebung im Projektordner.',
                  )
                : d.laeuft
                  ? t('🟢 geladen — belegt VRAM, gibt ihn nach {n} Min ohne Vorlesen frei', {
                      n: d.idle_min,
                    })
                  : t('⚪ VRAM frei — lädt beim ersten Vorlesen (ca. 15 s)')}
            </span>
            <span className={s.actionsFlex}>
              {!d.installiert && (
                <button
                  type="button"
                  className={s.btn}
                  disabled={laeuft}
                  onClick={() => void installieren()}
                >
                  {laeuft ? t('läuft…') : t('⬇ Installieren (~{dl} GB)', { dl: d.download_gb })}
                </button>
              )}
              {d.laeuft && (
                <button type="button" className={s.btn} onClick={() => void freigeben()}>
                  {t('⏹ VRAM freigeben')}
                </button>
              )}
              <Note text={note || installFehler} />
            </span>
            {(laeuft || d.install.log.length > 0) && !d.installiert && (
              <LogBox lines={d.install.log} />
            )}
          </span>
        </div>
      )}

      {an && d && (
        <div className={s.row}>
          <span className={s.grow}>
            <span className={s.t}>{t('Stimmprobe')}</span>
            <span className={s.d}>
              {t(
                'Die lokale Stimme ahmt diese Aufnahme nach: 10 bis 30 Sekunden, eine Person, ohne Musik. Nimm nur Stimmen, die du verwenden darfst.',
              )}{' '}
              {probe
                ? t('Hinterlegt: eigene Stimmprobe.')
                : t('Keine hinterlegt: eingebaute Standardstimme.')}
            </span>
            <span className={s.actionsFlex}>
              <button
                type="button"
                className={s.btn}
                title={t(
                  'Spricht einen kurzen Text mit der Gemini-Stimme von oben (eine Anfrage ans Kontingent).',
                )}
                onClick={() => void probeSetzen(probeAusGemini, '…')}
              >
                {t('🎙 Aus Gemini-Stimme erzeugen')}
              </button>
              <button type="button" className={s.btn} onClick={() => datei.current?.click()}>
                {t('📁 Datei wählen…')}
              </button>
              <input
                ref={datei}
                type="file"
                accept=".wav,.mp3,.flac,.ogg,audio/*"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  e.target.value = ''
                  if (f) void probeSetzen(() => probeHochladen(f), '…')
                }}
              />
              {probe && (
                <>
                  <button type="button" className={s.btn} onClick={probeAnhoeren}>
                    {t('▶ Probe anhören')}
                  </button>
                  <button
                    type="button"
                    className={s.btn}
                    title={t('Stimmprobe entfernen')}
                    onClick={() => void save({ tts: { probe: { [lang]: '' } } })}
                  >
                    ✕
                  </button>
                </>
              )}
              <button
                type="button"
                className={s.btn}
                disabled={!d.installiert}
                onClick={() => void hoerprobe()}
              >
                {t('▶ Hörprobe')}
              </button>
              <Note text={probeNote} />
            </span>
          </span>
        </div>
      )}
    </>
  )
}
