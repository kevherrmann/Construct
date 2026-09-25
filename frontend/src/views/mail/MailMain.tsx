import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router'
import { MAIL_KEYS } from '@/api/mail'
import { MailAccounts } from './MailAccounts'
import { MailCompose } from './MailCompose'
import { MailList } from './MailList'
import { MailRead } from './MailRead'
import { useMail } from './useMail'
import { useMailStore } from './mailStore'
import shared from './shared.module.css'

/**
 * Hauptbereich der Mail-Ansicht. Unterseiten als Routen, damit Zurück im
 * Browser funktioniert und andere Bereiche direkt hinspringen können:
 *   /mail            Liste
 *   /mail/msg?…      eine Mail lesen
 *   /mail/compose    schreiben (Vorbelegung aus dem Store)
 *   /mail/accounts   Konten verwalten (Ziel aus ⚙ Einstellungen)
 */
export function MailMain() {
  const qc = useQueryClient()
  const loc = useLocation()
  const nav = useNavigate()
  const { accountsQ, configured } = useMail()
  const draftSeq = useMailStore((st) => st.draftSeq)
  const filter = useMailStore((st) => st.filter)

  // Jede neue Seite (und jeder neue Filter) beginnt oben — wie früher.
  useEffect(() => {
    const scroller = document.querySelector('[data-scroll]')
    if (scroller) scroller.scrollTop = 0
  }, [loc.pathname, loc.search, filter])
  const entry = useRef(loc.pathname)
  const decided = useRef(false)

  // Beim Betreten der Ansicht frisch abrufen (alte Oberfläche: loadMailView) —
  // ohne force, der Server-Cache darf greifen.
  useEffect(() => {
    if (qc.getQueryState(MAIL_KEYS.list)?.dataUpdatedAt)
      void qc.refetchQueries({ queryKey: MAIL_KEYS.list }, { cancelRefetch: false })
  }, [qc])

  // Noch kein Konto eingerichtet? Dann beim Öffnen gleich zur Einrichtung —
  // aber nur beim Öffnen: ← Posteingang soll danach die (leere) Liste zeigen.
  useEffect(() => {
    // Lassen sich die Konten nicht laden, gilt das wie "keins eingerichtet":
    // die Einrichtung zeigt dann, was los ist.
    if (decided.current || accountsQ.isPending) return
    decided.current = true
    if (!configured && /^\/mail\/?$/.test(entry.current))
      void nav('/mail/accounts', { replace: true })
  }, [accountsQ.isPending, configured, nav])

  return (
    <div className={shared.main}>
      <Routes>
        <Route index element={<MailList />} />
        <Route path="msg" element={<MailRead />} />
        <Route path="compose" element={<MailCompose key={draftSeq} />} />
        <Route path="accounts" element={<MailAccounts />} />
        <Route path="*" element={<Navigate to="/mail" replace />} />
      </Routes>
    </div>
  )
}
