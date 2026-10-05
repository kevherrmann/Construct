import type { AuftragStatus } from '@/api/team'

/** Zeichen und Tönung je Zustand eines Auftrags. */
export const ZUSTAND: Record<
  AuftragStatus,
  { zeichen: string; art: '' | 'wartet' | 'fertig' | 'aus' }
> = {
  neu: { zeichen: '●', art: '' },
  laeuft: { zeichen: '⚙', art: '' },
  wartet_auf_kevin: { zeichen: '⏸', art: 'wartet' },
  wartet_auf_einstellung: { zeichen: '👥', art: 'wartet' },
  fertig: { zeichen: '✓', art: 'fertig' },
  abgebrochen: { zeichen: '✕', art: 'aus' },
}

export const wartetAufNutzer = (s: AuftragStatus) =>
  s === 'wartet_auf_kevin' || s === 'wartet_auf_einstellung'
