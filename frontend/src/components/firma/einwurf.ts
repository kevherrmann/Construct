import { useQueryClient } from '@tanstack/react-query'
import { useTeamChat, type ChatAuftrag } from '@/api/team'
import { apiPost } from '@/lib/api'

/** Der Auftrag, an dem die Firma in dieser Session gerade arbeitet (oder null).
 *  Wartet er auf den Nutzer, ist er nicht gemeint: dafür gibt es das Antwortfeld
 *  unter der Rückfrage. */
export function useArbeitenderAuftrag(sid: string | null | undefined): ChatAuftrag | null {
  const { data } = useTeamChat(sid)
  return data?.auftraege.find((a) => a.status === 'laeuft' || a.status === 'neu') ?? null
}

/** Eine Nachricht an die Firma statt an den Assistenten. Läuft gerade ein Zug, geht
 *  sie per stdin hinein (kein zusätzlicher Zug); sonst wartet sie als nächste
 *  Nachricht an die Geschäftsführung. Im Chat erscheint sie als Einwurf. */
export function useEinwurf() {
  const qc = useQueryClient()
  return async (auftrag: string, text: string) => {
    await apiPost(`/api/team/auftraege/${encodeURIComponent(auftrag)}/say`, { text })
    void qc.invalidateQueries({ queryKey: ['team'] })
  }
}
