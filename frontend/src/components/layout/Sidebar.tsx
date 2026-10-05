import { Suspense, type CSSProperties } from 'react'
import { NavLink } from 'react-router'
import { useTranslation } from 'react-i18next'
import { useSettings } from '@/stores/settings'
import { visibleViews, type ViewDef } from '@/views/registry'
import s from './Sidebar.module.css'

interface Props {
  view: ViewDef
  open: boolean
  onNavigate: () => void
}

export function Sidebar({ view, open, onNavigate }: Props) {
  const { t } = useTranslation()
  const tiles = useSettings((st) => st.settings.tiles)
  const assistant = useSettings((st) => st.boot.assistant)
  const views = visibleViews(tiles)
  // 1–4 Kacheln in eine Reihe, 5–6 als 3+3, mehr als 4+n.
  const spalten = views.length <= 4 ? views.length : views.length <= 6 ? 3 : 4
  return (
    <aside className={`${s.side} ${open ? s.open : ''}`}>
      {/* Der Ort heißt CONSTRUCT, der Assistent Cody. Beides gleich zu benennen
          ließ die App aussehen, als WÄRE sie er. */}
      <h1 className={s.brand}>◢◤ CONSTRUCT</h1>
      <div className={s.whoami}>
        <span className={s.dot}>●</span> {assistant.toUpperCase()}
      </div>
      <nav className={s.menu} style={{ '--spalten': spalten } as CSSProperties}>
        {views.map((v, i) => (
          <NavLink
            key={v.key}
            to={`/${v.key}`}
            onClick={onNavigate}
            className={({ isActive }) =>
              `${s.item} ${isActive ? s.active : ''} ${i % spalten === 0 ? s.links : ''} ${i < spalten ? s.oben : ''}`
            }
          >
            {v.icon}
            <span>{t(v.label)}</span>
          </NavLink>
        ))}
      </nav>
      <div className={s.panel}>
        <Suspense fallback={null}>
          <view.Side />
        </Suspense>
      </div>
    </aside>
  )
}
