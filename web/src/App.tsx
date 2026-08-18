import { Navigate, Route, Routes } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { LibraryPage } from './pages/LibraryPage'
import { FeedPage } from './pages/FeedPage'
import { ReaderPage } from './pages/ReaderPage'
import { VocabPage } from './pages/VocabPage'
import { WordDetailPage } from './pages/WordDetailPage'
import { ProtectedRoute } from './components/ProtectedRoute'

/** Everything behind the login wall renders inside ProtectedRoute. */
function Private({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute>{children}</ProtectedRoute>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <Private>
            <LibraryPage />
          </Private>
        }
      />
      <Route
        path="/shorts"
        element={
          <Private>
            <FeedPage />
          </Private>
        }
      />
      <Route
        path="/vocab"
        element={
          <Private>
            <VocabPage />
          </Private>
        }
      />
      <Route
        path="/reader/:lessonId"
        element={
          <Private>
            <ReaderPage />
          </Private>
        }
      />
      <Route
        path="/word/:word"
        element={
          <Private>
            <WordDetailPage />
          </Private>
        }
      />
      {/* The library used to live here. */}
      <Route path="/browse" element={<Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
