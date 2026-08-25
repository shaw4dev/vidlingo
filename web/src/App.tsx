// Route table, and the line between what a visitor can see and what needs an
// account.
//
// Browsing is public. The corpus is the product: a visitor who has to create an
// account before seeing a single video has no reason to create one. Everything
// that belongs to a *person* — the saved-word list, the account page — is what
// the login is actually for.
import { Navigate, Route, Routes } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { LibraryPage } from './pages/LibraryPage'
import { FeedPage } from './pages/FeedPage'
import { ReaderPage } from './pages/ReaderPage'
import { VocabPage } from './pages/VocabPage'
import { WordDetailPage } from './pages/WordDetailPage'
import { AccountPage } from './pages/AccountPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProtectedRoute } from './components/ProtectedRoute'

/** Everything behind the login wall renders inside ProtectedRoute. */
function Private({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute>{children}</ProtectedRoute>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Public: the library, the feed, the reader, a word's occurrences. */}
      <Route path="/" element={<LibraryPage />} />
      <Route path="/shorts" element={<FeedPage />} />
      <Route path="/reader/:lessonId" element={<ReaderPage />} />
      <Route path="/word/:word" element={<WordDetailPage />} />

      {/* Personal: needs an account. */}
      <Route
        path="/vocab"
        element={
          <Private>
            <VocabPage />
          </Private>
        }
      />
      <Route
        path="/account"
        element={
          <Private>
            <AccountPage />
          </Private>
        }
      />

      {/* The library used to live here. */}
      <Route path="/browse" element={<Navigate to="/" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
