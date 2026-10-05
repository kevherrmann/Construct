import { useEffect } from 'react'

/** Hält ein Menü offen, bis irgendwo sonst geklickt wird — oder Esc gedrückt. */
export function useSchliessen(open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return
    const f = () => close()
    const taste = (e: KeyboardEvent) => e.key === 'Escape' && close()
    document.addEventListener('click', f)
    document.addEventListener('keydown', taste)
    return () => {
      document.removeEventListener('click', f)
      document.removeEventListener('keydown', taste)
    }
  }, [open, close])
}
