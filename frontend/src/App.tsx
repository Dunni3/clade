import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import InboxPage from './pages/InboxPage';
import FeedPage from './pages/FeedPage';
import MessageDetailPage from './pages/MessageDetailPage';
import ComposePage from './pages/ComposePage';
import SettingsPage from './pages/SettingsPage';
import { useAuthStore } from './store/authStore';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const apiKey = useAuthStore((s) => s.apiKey);
  if (!apiKey) return <Navigate to="/settings" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/settings" element={<SettingsPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <InboxPage />
              </RequireAuth>
            }
          />
          <Route
            path="/feed"
            element={
              <RequireAuth>
                <FeedPage />
              </RequireAuth>
            }
          />
          <Route
            path="/messages/:id"
            element={
              <RequireAuth>
                <MessageDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/compose"
            element={
              <RequireAuth>
                <ComposePage />
              </RequireAuth>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
