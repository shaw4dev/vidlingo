import { Navigate, Route, Routes } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { FeedPage } from './pages/FeedPage'
import { BrowsePage } from './pages/BrowsePage'
import { ReaderPage } from './pages/ReaderPage'
import { WordDetailPage } from './pages/WordDetailPage'
import { ProtectedRoute } from './components/ProtectedRoute'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <FeedPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/browse"
        element={
          <ProtectedRoute>
            <BrowsePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reader/:lessonId"
        element={
          <ProtectedRoute>
            <ReaderPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/word/:word"
        element={
          <ProtectedRoute>
            <WordDetailPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
