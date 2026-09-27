import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import DashboardPage from './pages/DashboardPage'
import EventDetailPage from './pages/EventDetailPage'
import EventsPage from './pages/EventsPage'
import IntelligencePage from './pages/IntelligencePage'
import HealthPage from './pages/HealthPage'
import RiskPage from './pages/RiskPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/events/:id" element={<EventDetailPage />} />
          <Route path="/analytics" element={<IntelligencePage section="analytics" />} />
          <Route path="/risk" element={<RiskPage />} />
          <Route path="/model" element={<IntelligencePage section="model" />} />
          <Route path="/evidence" element={<IntelligencePage section="evidence" />} />
          <Route path="/health" element={<HealthPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
