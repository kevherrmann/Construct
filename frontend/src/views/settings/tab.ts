import { useSearchParams } from 'react-router'
import { getItem, setItem } from '@/lib/storage'
import { tabAus, type TabId } from './sections'

/** Gewählter Tab der Einstellungen: aus der Adresse (?tab=…, auch ein
 *  Abschnitt wie ?tab=telegram), sonst der zuletzt gewählte. */
export function useSettingsTab(): [TabId, (t: TabId) => void] {
  const [params, setParams] = useSearchParams()
  const tab = tabAus(params.get('tab')) ?? tabAus(getItem('mxsettab')) ?? 'allgemein'
  const setTab = (neu: TabId) => {
    setItem('mxsettab', neu)
    setParams({ tab: neu }, { replace: true })
  }
  return [tab, setTab]
}
