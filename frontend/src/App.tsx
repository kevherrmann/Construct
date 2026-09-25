import { readBootstrap } from '@/lib/bootstrap'

const boot = readBootstrap()

// Platzhalter für Phase 0 — das echte Grundgerüst (Seitenleiste, Ansichten)
// kommt in Phase 1.
export default function App() {
  return (
    <main style={{ padding: 40, fontFamily: 'monospace' }}>
      <h1>CONSTRUCT // next</h1>
      <p>
        {boot.assistant} · {boot.lang} · theme: {boot.settings.theme}
      </p>
    </main>
  )
}
