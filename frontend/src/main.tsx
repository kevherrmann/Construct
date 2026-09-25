import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { initI18n } from '@/lib/i18n'
import { applyTheme } from '@/lib/themes'
import { useSettings } from '@/stores/settings'
import './styles/global.css'

const { boot } = useSettings.getState()
initI18n(boot.lang)
applyTheme(boot.settings.theme)

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
