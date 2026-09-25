import { useTranslation } from 'react-i18next'
import { useMailAccounts, useMailCategories, useMailList } from '@/api/mail'
import { locale } from '@/lib/i18n'
import { useSettings } from '@/stores/settings'

/** Alles, was Seitenleiste und Hauptbereich gemeinsam brauchen. */
export function useMail() {
  const accountsQ = useMailAccounts()
  const catsQ = useMailCategories()
  const accounts = accountsQ.data ?? []
  const configured = accounts.some((a) => a.configured)
  const listQ = useMailList(configured)
  return {
    accountsQ,
    accounts,
    categories: catsQ.data ?? [],
    configured,
    listQ,
    msgs: listQ.data?.messages ?? [],
    errors: listQ.data?.errors ?? {},
    /** Mindestens einmal geladen (alte Oberfläche: mailLoaded). */
    loaded: listQ.data !== undefined,
  }
}

/** Texte vom Server (Anbieter-Hinweise, Fehlermeldungen) sind deutsch; die
 *  bekannten stehen im Wörterbuch, unbekannte bleiben einfach, wie sie sind. */
export function useServerText() {
  const { t } = useTranslation()
  return (s: string) => (s ? t(s) : s)
}

export const useLocale = () => locale(useSettings((s) => s.boot.lang))
