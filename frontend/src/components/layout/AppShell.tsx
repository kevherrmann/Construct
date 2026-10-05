import { useUi } from '@/stores/ui'
import { useChat } from '@/stores/chat'
import { Suspense, useEffect } from 'react'
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
import { RaumView } from '@/views/raum/RaumView'
import s from './AppShell.module.css'

export function AppShell() {
  const { view } = useParams()
  const tiles = useSettings((st) => st.settings.tiles)
  const assistant = useSettings((st) => st.boot.assistant)
  const sideOpen = useUi((st) => st.sideOpen)
  const setSideOpen = useUi((st) => st.setSideOpen)
  const raum = useUi((st) => st.raum)
  // Schmal: wer eine Session wählt, will sie sehen — die Seitenleiste klappt zu.
  const activeKey = useChat((st) => st.activeKey)
  useEffect(() => {
    setSideOpen(false)
  }, [activeKey, setSideOpen])

  useEffect(() => {
    document.title = `CONSTRUCT // ${assistant}`
  }, [assistant])

  // Unbekannte Ansichten führen zum Chat; abgeschaltete zu den Einstellungen —
  // dort hat man sie gerade abgeschaltet und kann sie wieder einschalten.
  const current = visibleViews(tiles).find((v) => v.key === view)
  if (!current) {
    const known = VIEWS.some((v) => v.key === view)
    return <Navigate to={known ? '/settings' : `/${VIEWS[0]!.key}`} replace />
  }

  // Construct-Raum: dieselben Stores, andere Bühne. Ohne Matrix-Regen
  // dahinter — der Raum ist weiß und deckt alles ab.
  if (raum)
    return (
      <>
        <RaumView />
        <UpdateCard />
        <ProvidersDialog />
        <LoginDialog />
        <ClaudeSetupDialog />
      </>
    )

  return (
    <>
      <Backdrop />
      <div className={s.app}>
        {sideOpen && <div className={s.scrim} onClick={() => setSideOpen(false)} />}
        <Sidebar view={current} open={sideOpen} onNavigate={() => setSideOpen(false)} />
        <SideGrip />
        <section className={s.main}>
          <Topbar onBurger={() => setSideOpen(!sideOpen)} />
          {/* Scroll-Container für alle Ansichten (früher #chat). Die Eingabe steht
            immer darunter — wer aus dem Kalender schreibt, landet im Chat.
            key je Ansicht: sonst behielt z.B. der Kalender die Scrollposition
            des Chats und begann mittendrin. */}
          <div key={current.key} className={s.content} data-scroll>
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
