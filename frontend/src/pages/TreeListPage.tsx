import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getTrees } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import type { TreeSummary } from '../types/mailbox';

const statusColors: Record<string, string> = {
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
  in_progress: 'bg-amber-500/20 text-amber-300',
  pending: 'bg-gray-500/20 text-gray-300',
  killed: 'bg-orange-500/20 text-orange-300',
  blocked: 'bg-yellow-500/20 text-yellow-300',
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

export default function TreeListPage() {
  const [trees, setTrees] = useState<TreeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const apiKey = useAuthStore((s) => s.apiKey);

  useEffect(() => {
    if (!apiKey) return;
    setLoading(true);
    getTrees({ limit: 50 })
      .then(setTrees)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, [apiKey]);

  if (!apiKey) {
    return <p className="text-gray-400">Set your API key in <a href="/settings" className="text-indigo-400 underline">Settings</a> first.</p>;
  }

  const statusEntries: { key: keyof TreeSummary; label: string }[] = [
    { key: 'completed', label: 'completed' },
    { key: 'in_progress', label: 'in_progress' },
    { key: 'pending', label: 'pending' },
    { key: 'blocked', label: 'blocked' },
    { key: 'failed', label: 'failed' },
    { key: 'killed', label: 'killed' },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Trees</h1>
      {loading && <p className="text-gray-500">Loading...</p>}
      {error && <p className="text-red-400">{error}</p>}
      {!loading && trees.length === 0 && <p className="text-gray-500">No task trees.</p>}
      <div className="space-y-2">
        {trees.map((tree) => (
          <Link
            key={tree.root_task_id}
            to={`/trees/${tree.root_task_id}`}
            className="block rounded-lg border border-gray-800 p-4 transition-colors hover:bg-gray-800/50"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-gray-500">#{tree.root_task_id}</span>
                  <span className="text-xs text-gray-500">{tree.creator}</span>
                  <span className="text-xs text-gray-600">{tree.total_tasks} task{tree.total_tasks !== 1 ? 's' : ''}</span>
                </div>
                <p className="text-sm text-gray-300 truncate">
                  {tree.subject || '(no subject)'}
                </p>
                <div className="flex items-center gap-1.5 mt-2">
                  {statusEntries.map(({ key, label }) => {
                    const count = tree[key] as number;
                    if (count === 0) return null;
                    return (
                      <span
                        key={label}
                        className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${statusColors[label] || 'bg-gray-700 text-gray-300'}`}
                      >
                        {count} {label}
                      </span>
                    );
                  })}
                </div>
              </div>
              <span className="text-xs text-gray-500 whitespace-nowrap">{formatDate(tree.created_at)}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
