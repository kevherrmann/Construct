import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '@/lib/queryClient'
import App from './App'
import { initI18n } from '@/lib/i18n'
import { applyTheme } from '@/lib/themes'
import { useSettings } from '@/stores/settings'
import { installExternalLinkHandler } from '@/lib/externalLinks'
import { fxLevel } from '@/lib/fx'
import './styles/global.css'

const { boot } = useSettings.getState()
initI18n(boot.lang)
applyTheme(boot.settings.theme)
installExternalLinkHandler()
document.body.classList.toggle('fx-off', fxLevel() === 'off')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
