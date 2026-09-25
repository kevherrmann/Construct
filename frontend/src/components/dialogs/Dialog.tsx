import type { ReactNode } from 'react'
import * as RD from '@radix-ui/react-dialog'
import { useTranslation } from 'react-i18next'
import s from './Dialog.module.css'

interface Props {
  open: boolean
  onClose: () => void
  title: string
  wide?: boolean
  children: ReactNode
}

// Gemeinsamer Rahmen der App-Dialoge: abgedunkelte Maske, Box mit ✕.
// Radix kümmert sich um Fokus-Falle, Esc und Klick daneben.
export function Dialog({ open, onClose, title, wide, children }: Props) {
  const { t } = useTranslation()
  return (
    <RD.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <RD.Portal>
        {/* Box IN der Maske: so zentriert Flexbox sie, und langer Inhalt scrollt. */}
        <RD.Overlay className={s.mask}>
          <RD.Content className={`${s.box} ${wide ? s.wide : ''}`} aria-describedby={undefined}>
            <RD.Close className={s.close} title={t('schließen')}>
              ✕
            </RD.Close>
            <RD.Title asChild>
              <h3>{title}</h3>
            </RD.Title>
            {children}
          </RD.Content>
        </RD.Overlay>
      </RD.Portal>
    </RD.Root>
  )
}
