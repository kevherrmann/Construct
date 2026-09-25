import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// Die neue Oberfläche wächst parallel zur alten unter /next. Der Build landet
// im Repo (static/next), damit Nutzer ohne Node.js installieren und per
// `git pull` aktualisieren können — siehe README, Abschnitt Frontend.
const BACKEND = process.env.CONSTRUCT_BACKEND ?? 'http://127.0.0.1:8765'

export default defineConfig({
  base: '/next/',
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    outDir: '../static/next',
    emptyOutDir: true,
    // Das Desktop-Fenster läuft unter Linux in WebKitGTK — dort sind ältere
    // Versionen verbreitet. Lieber konservativ übersetzen als eine leere Seite.
    target: ['es2020', 'safari14'],
    // Das Start-Paket trägt Markdown und Code-Hervorhebung (highlight.js), die
    // der Chat sofort braucht. Geladen wird von localhost, nicht übers Netz —
    // ~210 kB gzip sind hier kein Problem. Alle anderen Ansichten laden erst
    // beim Öffnen (views/registry.tsx).
    chunkSizeWarningLimit: 800,
  },
  server: {
    port: 5173,
    // Im Entwicklungsmodus liefert Vite die Oberfläche, alles andere kommt vom
    // laufenden CONSTRUCT-Server.
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/uploads': { target: BACKEND, changeOrigin: true },
      '/static': { target: BACKEND, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
