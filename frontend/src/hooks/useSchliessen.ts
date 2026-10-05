import { useEffect } from 'react'

/** Hält ein Menü offen, bis irgendwo sonst geklickt wird. */
export function useSchliessen(open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return
    const f = () => close()
    document.addEventListener('click', f)
    return () => document.removeEventListener('click', f)
  }, [open, close])
}
