import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { errText, mailApi, patchMailList, type MailRef } from '@/api/mail'
import { mailKey, useMailStore } from './mailStore'
import { useServerText } from './useMail'

/** Einzelne Mail löschen (auch auf dem Server → Papierkorb). true = gelöscht. */
export function useDeleteMail() {
  const { t } = useTranslation()
  const st = useServerText()
  const qc = useQueryClient()
  const toggle = useMailStore((s) => s.toggle)
  return async (m: MailRef & { subject: string }) => {
    if (
      !window.confirm(
        `${t('E-Mail wirklich löschen?')}\n\n„${m.subject || t('(kein Betreff)')}“\n\n` +
          t('Sie wird auch auf dem Mail-Server in den Papierkorb verschoben.'),
      )
    )
      return false
    try {
      await mailApi.delete({ account: m.account, uid: m.uid, folder: m.folder || 'INBOX' })
    } catch (e) {
      window.alert(t('Löschen fehlgeschlagen:') + ' ' + st(errText(e)))
      return false
    }
    patchMailList(qc, (ms) => ms.filter((x) => !(x.account === m.account && x.uid === m.uid)))
    toggle(mailKey(m), false)
    return true
  }
}
