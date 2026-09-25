import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocalStorage } from '@/hooks/useLocalStorage'
import s from './SideGrip.module.css'

const MIN = 220
const clamp = (w: number) => Math.round(Math.max(MIN, Math.min(w, Math.min(900, innerWidth * 0.6))))

// Seitenleiste in der Breite ziehen. Pointer-Capture statt mousemove am
// document: so geht der Zug nicht verloren, wenn die Maus über den Inhalt oder
// aus dem Fenster rutscht. Doppelklick = zurück auf Standard. Derselbe
// Speicherschlüssel wie die alte Oberfläche, damit die Breite erhalten bleibt.
export function SideGrip() {
  const { t } = useTranslation()
  const [stored, setStored] = useLocalStorage('sideW')
  const [drag, setDrag] = useState(false)
  const start = useRef({ x: 0, w: 0 })

  useEffect(() => {
    const root = document.documentElement
    if (stored) root.style.setProperty('--side-w', `${clamp(Number(stored))}px`)
    else root.style.removeProperty('--side-w')
  }, [stored])

  const width = () => document.querySelector('aside')?.getBoundingClientRect().width ?? 300

  const down = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    start.current = { x: e.clientX, w: width() }
    setDrag(true)
    document.body.classList.add('side-drag')
  }
  const move = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return
    const w = clamp(start.current.w + e.clientX - start.current.x)
    document.documentElement.style.setProperty('--side-w', `${w}px`)
  }
  const up = () => {
    if (!drag) return
    setDrag(false)
    document.body.classList.remove('side-drag')
    setStored(String(Math.round(width())))
  }

  return (
    <div
      className={`${s.grip} ${drag ? s.drag : ''}`}
      title={t('Ziehen = Breite ändern · Doppelklick = Standard')}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onDoubleClick={() => setStored(null)}
    />
  )
}
