import { useContext, type ElementType, type ReactNode } from 'react'
import { Plasma } from '@cruxgarden/plasma-ui'
import { PlasmaActive } from './plasmaContext'

// Große Fläche der Oberfläche (Seitenleiste, Statusleiste, Eingabe, Dialog).
// Im Plasma-Theme wird sie zu einer flüssigen Glas-Fläche; sonst ist sie ein
// ganz normales Element. Die Fläche selbst malt der Plasma-Canvas — das
// Element darüber bleibt durchsichtig und trägt nur den Inhalt.

interface Props {
  as?: ElementType
  className?: string
  children?: ReactNode
  /** Schwebt über den anderen (Dialoge, Karten). */
  elevation?: number
  radius?: number
  /** Verschmilzt mit Nachbarn, wenn sie sich nahekommen. */
  fuse?: boolean
  [k: string]: unknown
}

export function Surface({
  as = 'div',
  className,
  children,
  elevation,
  radius,
  fuse = true,
  ...rest
}: Props) {
  const live = useContext(PlasmaActive)
  if (!live) {
    const El = as
    return (
      <El className={className} {...rest}>
        {children}
      </El>
    )
  }
  return (
    <Plasma
      as={as}
      className={className}
      lean={false}
      fuse={fuse}
      elevation={elevation}
      radius={radius}
      {...rest}
    >
      {children}
    </Plasma>
  )
}
