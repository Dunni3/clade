import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { getThrums, getMemberActivity } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import type { ThrumSummary } from '../types/mailbox';

const STATUSES = ['', 'pending', 'planning', 'active', 'paused', 'completed', 'failed'];
const PRIORITIES = ['', 'low', 'normal', 'high', 'urgent'];

const statusColors: Record<string, string> = {
  pending: 'bg-gray-500/20 text-gray-300',
  planning: 'bg-blue-500/20 text-blue-300',
  active: 'bg-amber-500/20 text-amber-300',
  paused: 'bg-purple-500/20 text-purple-300',
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
};

const priorityColors: Record<string, string> = {
  low: 'bg-gray-500/20 text-gray-400',
  normal: 'bg-blue-500/20 text-blue-300',
  high: 'bg-amber-500/20 text-amber-300',
  urgent: 'bg-red-500/20 text-red-300',
};

function formatDate(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 86400000) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  if (diff < 604800000) {
    return d.toLocaleDateString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export default function ThrumListPage() {
  const [thrums, setThrums] = useState<ThrumSummary[]>([]);
  const [members, setMembers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [creator, setCreator] = useState('');
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const apiKey = useAuthStore((s) => s.apiKey);

  useEffect(() => {
    if (!apiKey) return;
    getMemberActivity()
      .then((res) => setMembers(res.members.map((m) => m.name)))
      .catch(() => {});
  }, [apiKey]);

  const fetchThrums = useCallback(async () => {
    if (!apiKey) return;
    setLoading(true);
    try {
      const params: Record<string, string | number> = { limit: 50 };
      if (creator) params.creator = creator;
      if (status) params.status = status;
      const data = await getThrums(params);
      // Client-side priority filter (API doesn't support it)
      const filtered = priority ? data.filter((t) => t.priority === priority) : data;
      setThrums(filtered);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [apiKey, creator, status, priority]);

  useEffect(() => {
    fetchThrums();
  }, [fetchThrums]);

  if (!apiKey) {
    return <p className="text-gray-400">Set your API key in <a href="/settings" className="text-indigo-400 underline">Settings</a> first.</p>;
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Thrums</h1>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
        >
          <option value="">All statuses</option>
          {STATUSES.filter(Boolean).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={creator}
          onChange={(e) => setCreator(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
        >
          <option value="">All creators</option>
          {members.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
        >
          <option value="">All priorities</option>
          {PRIORITIES.filter(Boolean).map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>
      {loading && <p className="text-gray-500">Loading...</p>}
      {error && <p className="text-red-400">{error}</p>}
      {!loading && thrums.length === 0 && <p className="text-gray-500">No thrums.</p>}
      <div className="space-y-2">
        {thrums.map((thrum) => (
          <Link
            key={thrum.id}
            to={`/thrums/${thrum.id}`}
            className="block rounded-lg border border-gray-800 p-4 transition-colors hover:bg-gray-800/50"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-gray-500">#{thrum.id}</span>
                  <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${statusColors[thrum.status] || 'bg-gray-700 text-gray-300'}`}>
                    {thrum.status}
                  </span>
                  <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${priorityColors[thrum.priority] || 'bg-gray-700 text-gray-300'}`}>
                    {thrum.priority}
                  </span>
                  <span className="text-xs text-gray-500">{thrum.creator}</span>
                </div>
                <p className="text-sm text-gray-300 truncate">
                  {thrum.title || '(no title)'}
                </p>
                {thrum.goal && (
                  <p className="text-xs text-gray-500 truncate mt-0.5">{thrum.goal}</p>
                )}
              </div>
              <span className="text-xs text-gray-500 whitespace-nowrap">{formatDate(thrum.created_at)}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
