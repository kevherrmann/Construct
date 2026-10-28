import { useSyncExternalStore } from 'react'
import { abonnieren, ruhtJetzt } from '@/lib/ruhe'

/** Sieht gerade keiner hin (lib/ruhe.ts)? Dann darf Deko anhalten, die sonst
 *  ständig zeichnet. */
export function useRuhe(): boolean {
  return useSyncExternalStore(abonnieren, ruhtJetzt)
}
