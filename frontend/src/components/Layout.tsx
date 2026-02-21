import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { getUnreadCount } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';

const navItems = [
  { to: '/', label: 'Inbox' },
  { to: '/feed', label: 'Feed' },
  { to: '/tasks', label: 'Tasks' },
  { to: '/trees', label: 'Trees' },
  { to: '/board', label: 'Board' },
  { to: '/morsels', label: 'Morsels' },
  { to: '/status', label: 'Status' },
  { to: '/compose', label: 'Compose' },
  { to: '/settings', label: 'Settings' },
];

export default function Layout() {
  const [unread, setUnread] = useState(0);
  const apiKey = useAuthStore((s) => s.apiKey);
  const location = useLocation();

  // Refresh unread count on route changes and every 30s
  useEffect(() => {
    if (!apiKey) return;
    getUnreadCount().then(setUnread).catch(() => {});
  }, [apiKey, location.pathname]);

  useEffect(() => {
    if (!apiKey) return;
    const interval = setInterval(() => {
      getUnreadCount().then(setUnread).catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, [apiKey]);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="border-b border-gray-800 bg-gray-900">
        <div className="mx-auto max-w-6xl flex items-center gap-1 px-4 py-3">
          <span className="text-lg font-bold text-indigo-400 mr-6">The Hearth</span>
          {navItems.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`
              }
            >
              {label}
              {label === 'Inbox' && unread > 0 && (
                <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-xs font-bold text-white">
                  {unread}
                </span>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
