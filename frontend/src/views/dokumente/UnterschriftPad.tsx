import { useRef, useState, type PointerEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useDokumenteAktionen } from '@/api/dokumente'
import { Dialog } from '@/components/dialogs/Dialog'
import s from './Dokumente.module.css'

// Tintenfarben: das ist Inhalt des Dokuments, keine Oberfläche, darum fest und nicht aus dem Theme.
const TINTE = { blau: '#1b2f8a', schwarz: '#151515' } as const

interface Props {
  open: boolean
  onClose: () => void
  onGespeichert: () => void
}

// Unterschrift einmal hinterlegen: mit Maus, Finger oder Stift zeichnen, oder ein Foto davon laden.
export function UnterschriftPad({ open, onClose, onGespeichert }: Props) {
  const { t } = useTranslation()
  const act = useDokumenteAktionen()
  const leinwand = useRef<HTMLCanvasElement | null>(null)
  const letzter = useRef<{ x: number; y: number } | null>(null)
  const [tinte, setTinte] = useState<keyof typeof TINTE>('blau')
  const [leer, setLeer] = useState(true)
  const [fehler, setFehler] = useState('')

  // Leinwand in Gerätepixeln, sonst wird die Linie auf hochauflösenden Schirmen unscharf.
  // Radix hängt den Inhalt erst nach dem Öffnen ein: darum per Callback-Ref statt Effekt.
  const einrichten = (c: HTMLCanvasElement | null) => {
    leinwand.current = c
    if (!c || c.dataset.bereit) return
    const r = window.devicePixelRatio || 1
    c.width = Math.round(c.clientWidth * r)
    c.height = Math.round(c.clientHeight * r)
    c.dataset.bereit = '1'
  }
  const punkt = (e: PointerEvent<HTMLCanvasElement>) => {
    const c = e.currentTarget
    const b = c.getBoundingClientRect()
    return {
      x: ((e.clientX - b.left) * c.width) / b.width,
      y: ((e.clientY - b.top) * c.height) / b.height,
    }
  }
  const strich = (e: PointerEvent<HTMLCanvasElement>) => {
    const c = e.currentTarget
    const g = c.getContext('2d')
    const von = letzter.current
    if (!g || !von) return
    const nach = punkt(e)
    const r = window.devicePixelRatio || 1
    // Stift mit Druck: etwas dicker bei mehr Druck. Maus meldet 0,5.
    const druck = e.pointerType === 'pen' && e.pressure > 0 ? e.pressure : 0.5
    g.strokeStyle = TINTE[tinte]
    g.lineWidth = (1.6 + druck * 2.4) * r
    g.lineCap = 'round'
    g.lineJoin = 'round'
    g.beginPath()
    g.moveTo(von.x, von.y)
    // Über die Mitte glätten: aus Ecken werden Bögen
    const mitte = { x: (von.x + nach.x) / 2, y: (von.y + nach.y) / 2 }
    g.quadraticCurveTo(von.x, von.y, mitte.x, mitte.y)
    g.lineTo(nach.x, nach.y)
    g.stroke()
    letzter.current = nach
    setLeer(false)
  }
  const leeren = () => {
    const c = leinwand.current
    c?.getContext('2d')?.clearRect(0, 0, c.width, c.height)
    setLeer(true)
  }
  const schliessen = () => {
    setLeer(true)
    setFehler('')
    onClose()
  }
  const hochladen = async (bild: Blob) => {
    setFehler('')
    try {
      await act.unterschriftSpeichern.mutateAsync(bild)
      onGespeichert()
      schliessen()
    } catch (e) {
      setFehler((e as Error).message)
    }
  }
  const speichern = () => leinwand.current?.toBlob((b) => b && void hochladen(b), 'image/png')

  return (
    <Dialog open={open} onClose={schliessen} title={t('Unterschrift hinterlegen')} wide>
      <div className={s.form}>
        <p className={s.erklaer}>
          {t(
            'Unterschreib im Feld mit Maus, Finger oder Stift. Oder lade ein Foto deiner Unterschrift auf weißem Papier, der Hintergrund wird entfernt.',
          )}
        </p>
        <canvas
          ref={einrichten}
          className={s.pad}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId)
            letzter.current = punkt(e)
          }}
          onPointerMove={(e) => letzter.current && strich(e)}
          onPointerUp={() => (letzter.current = null)}
          onPointerCancel={() => (letzter.current = null)}
        />
        <div className={s.aktionen}>
          {(Object.keys(TINTE) as (keyof typeof TINTE)[]).map((k) => (
            <label key={k} className={s.leise}>
              <input type="radio" name="tinte" checked={tinte === k} onChange={() => setTinte(k)} />{' '}
              {k === 'blau' ? t('blau') : t('schwarz')}
            </label>
          ))}
          <button type="button" className={s.link} onClick={leeren}>
            {t('neu zeichnen')}
          </button>
        </div>
        {fehler && <div className={s.fehler}>{fehler}</div>}
        <div className={s.aktionen}>
          <button
            type="button"
            className={`${s.knopf} ${s.voll}`}
            disabled={leer || act.unterschriftSpeichern.isPending}
            onClick={speichern}
          >
            {t('SPEICHERN')}
          </button>
          <label className={s.knopf}>
            {t('FOTO LADEN')}
            <input
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0]
                e.target.value = ''
                if (f) void hochladen(f)
              }}
            />
          </label>
        </div>
      </div>
    </Dialog>
  )
}
