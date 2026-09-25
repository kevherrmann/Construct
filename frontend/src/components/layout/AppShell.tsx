import { Suspense, useEffect, useState } from 'react'
import { Navigate, useParams } from 'react-router'
import { useSettings } from '@/stores/settings'
import { visibleViews, VIEWS } from '@/views/registry'
import { Sidebar } from './Sidebar'
import { SideGrip } from './SideGrip'
import { Topbar } from './Topbar'
import { Composer } from '@/components/chat/Composer'
import { Backdrop } from './Backdrop'
import { UpdateCard } from './UpdateCard'
import { LoginDialog, ClaudeSetupDialog } from '@/components/dialogs/LoginDialog'
import { ProvidersDialog } from '@/components/dialogs/ProvidersDialog'
import s from './AppShell.module.css'

export function AppShell() {
  const { view } = useParams()
  const tiles = useSettings((st) => st.settings.tiles)
  const assistant = useSettings((st) => st.boot.assistant)
  const [sideOpen, setSideOpen] = useState(false)

  useEffect(() => {
    document.title = `CONSTRUCT // ${assistant}`
  }, [assistant])

  // Abgeschaltete oder unbekannte Ansichten führen zum Chat.
  const current = visibleViews(tiles).find((v) => v.key === view)
  if (!current) return <Navigate to={`/${VIEWS[0]!.key}`} replace />

  return (
    <>
      <Backdrop />
      <div className={s.app}>
        <Sidebar view={current} open={sideOpen} onNavigate={() => setSideOpen(false)} />
        <SideGrip />
        <section className={s.main}>
          <Topbar onBurger={() => setSideOpen((o) => !o)} />
          {/* Scroll-Container für alle Ansichten (früher #chat). Die Eingabe steht
            immer darunter — wer aus dem Kalender schreibt, landet im Chat. */}
          <div className={s.content} data-scroll>
            <Suspense fallback={null}>
              <current.Main />
            </Suspense>
          </div>
          <Composer />
        </section>
      </div>
      <UpdateCard />
      {/* App-weite Dialoge, einmal gerendert; öffnen über stores/dialogs. */}
      <ProvidersDialog />
      <LoginDialog />
      <ClaudeSetupDialog />
    </>
  )
}
