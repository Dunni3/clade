import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import InboxPage from './pages/InboxPage';
import FeedPage from './pages/FeedPage';
import MessageDetailPage from './pages/MessageDetailPage';
import ComposePage from './pages/ComposePage';
import TasksPage from './pages/TasksPage';
import TaskDetailPage from './pages/TaskDetailPage';
import TreeListPage from './pages/TreeListPage';
import TreeDetailPage from './pages/TreeDetailPage';
import KanbanPage from './pages/KanbanPage';
import CardDetailPage from './pages/CardDetailPage';
import MorselFeedPage from './pages/MorselFeedPage';
import MorselDetailPage from './pages/MorselDetailPage';
import StatusPage from './pages/StatusPage';
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
            path="/tasks"
            element={
              <RequireAuth>
                <TasksPage />
              </RequireAuth>
            }
          />
          <Route
            path="/tasks/:id"
            element={
              <RequireAuth>
                <TaskDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/trees"
            element={
              <RequireAuth>
                <TreeListPage />
              </RequireAuth>
            }
          />
          <Route
            path="/trees/:rootId"
            element={
              <RequireAuth>
                <TreeDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/board"
            element={
              <RequireAuth>
                <KanbanPage />
              </RequireAuth>
            }
          />
          <Route
            path="/board/cards/:id"
            element={
              <RequireAuth>
                <CardDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/morsels"
            element={
              <RequireAuth>
                <MorselFeedPage />
              </RequireAuth>
            }
          />
          <Route
            path="/morsels/:id"
            element={
              <RequireAuth>
                <MorselDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/status"
            element={
              <RequireAuth>
                <StatusPage />
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
