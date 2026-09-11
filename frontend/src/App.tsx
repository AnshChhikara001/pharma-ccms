import { Navigate, Route, Routes } from 'react-router-dom'

import AppShell from '@/features/auth/AppShell'
import LoginPage from '@/features/auth/LoginPage'
import { useAppSelector } from '@/app/store'
import ComplaintDetailPage from '@/features/complaints/ComplaintDetailPage'
import ComplaintsPage from '@/features/complaints/ComplaintsPage'
import IntakePage from '@/features/complaints/IntakePage'

export default function App() {
  const token = useAppSelector((state) => state.auth.token)

  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to="/complaints" replace /> : <LoginPage />} />
      <Route element={token ? <AppShell /> : <Navigate to="/login" replace />}>
        <Route path="/complaints" element={<ComplaintsPage />} />
        <Route path="/complaints/new" element={<IntakePage />} />
        <Route path="/complaints/:complaintId" element={<ComplaintDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to={token ? '/complaints' : '/login'} replace />} />
    </Routes>
  )
}
