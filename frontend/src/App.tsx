import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AppShell } from '@/components/layout/AppShell'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/:view/*" element={<AppShell />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
