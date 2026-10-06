// Route table, and the line between what a visitor can see and what needs an
// account.
//
// Browsing is public. The corpus is the product: a visitor who has to create an
// account before seeing a single video has no reason to create one. Everything
// that belongs to a *person* — the saved-word list, the review schedule, the
// account page — is what the login is actually for.
//
// The two personal *features* do not redirect when signed out; they render
// their own case for an account in place (SignUpGate), because a person who
// clicked Review has just told us they are interested and a redirect throws
// that away. Only /account, which is meaningless without an account, bounces.
import { Navigate, Route, Routes } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { ExplorePage } from './pages/ExplorePage'
import { LibraryPage } from './pages/LibraryPage'
import { FeedPage } from './pages/FeedPage'
import { ReaderPage } from './pages/ReaderPage'
import { ReviewPage } from './pages/ReviewPage'
import { VocabPage } from './pages/VocabPage'
import { WordDetailPage } from './pages/WordDetailPage'
import { AccountPage } from './pages/AccountPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProtectedRoute } from './components/ProtectedRoute'
import { GATES } from './components/gates'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/welcome" element={<OnboardingPage />} />

      {/* Public: explore, the full library, the feed, the reader, a word. */}
      <Route path="/" element={<ExplorePage />} />
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/shorts" element={<FeedPage />} />
      <Route path="/reader/:lessonId" element={<ReaderPage />} />
      <Route path="/word/:word" element={<WordDetailPage />} />

      {/* Personal: needs an account, and says why. */}
      <Route
        path="/review"
        element={
          <ProtectedRoute gate={GATES.review}>
            <ReviewPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/vocab"
        element={
          <ProtectedRoute gate={GATES.vocab}>
            <VocabPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/account"
        element={
          <ProtectedRoute>
            <AccountPage />
          </ProtectedRoute>
        }
      />

      {/* The library used to be the landing page, and lived here before that. */}
      <Route path="/browse" element={<Navigate to="/library" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
