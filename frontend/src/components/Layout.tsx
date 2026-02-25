import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { getUnreadCount } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import Spotlight from './Spotlight';

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
  const [spotlightOpen, setSpotlightOpen] = useState(false);
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

  // Global Cmd+K / Ctrl+K listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSpotlightOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

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
          <button
            onClick={() => setSpotlightOpen(true)}
            className="ml-auto flex items-center gap-2 px-3 py-1.5 rounded text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-xs font-mono text-gray-500 bg-gray-800 border border-gray-700 rounded">
              &#x2318;K
            </kbd>
          </button>
        </div>
      </nav>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
      <Spotlight open={spotlightOpen} onClose={() => setSpotlightOpen(false)} />
    </div>
  );
}
