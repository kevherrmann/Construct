import { Akte } from './Akte'
import { OrgChart } from './OrgChart'
import { UserMd } from './UserMd'
import { usePersonal } from './store'

export function PersonalMain() {
  const { ansicht, slug } = usePersonal()
  if (ansicht === 'akte' && slug) return <Akte slug={slug} />
  if (ansicht === 'user') return <UserMd />
  return <OrgChart />
}
