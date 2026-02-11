import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { getTasks } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import type { TaskSummary } from '../types/mailbox';

const BROTHERS = ['', 'ian', 'doot', 'oppy', 'jerry'];
const STATUSES = ['', 'pending', 'launched', 'in_progress', 'completed', 'failed'];

const statusColors: Record<string, string> = {
  pending: 'bg-gray-500/20 text-gray-300',
  launched: 'bg-blue-500/20 text-blue-300',
  in_progress: 'bg-amber-500/20 text-amber-300',
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
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

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [assignee, setAssignee] = useState('');
  const [status, setStatus] = useState('');
  const apiKey = useAuthStore((s) => s.apiKey);

  const fetchTasks = useCallback(async () => {
    if (!apiKey) return;
    setLoading(true);
    try {
      const params: Record<string, string | number> = { limit: 50 };
      if (assignee) params.assignee = assignee;
      if (status) params.status = status;
      const data = await getTasks(params);
      setTasks(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [apiKey, assignee, status]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  if (!apiKey) {
    return <p className="text-gray-400">Set your API key in <a href="/settings" className="text-indigo-400 underline">Settings</a> first.</p>;
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Tasks</h1>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
        >
          <option value="">All assignees</option>
          {BROTHERS.filter(Boolean).map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
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
      </div>
      {loading && <p className="text-gray-500">Loading...</p>}
      {error && <p className="text-red-400">{error}</p>}
      {!loading && tasks.length === 0 && <p className="text-gray-500">No tasks.</p>}
      <div className="space-y-2">
        {tasks.map((task) => (
          <Link
            key={task.id}
            to={`/tasks/${task.id}`}
            className="block rounded-lg border border-gray-800 p-4 transition-colors hover:bg-gray-800/50"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-gray-500">#{task.id}</span>
                  <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${statusColors[task.status] || 'bg-gray-700 text-gray-300'}`}>
                    {task.status}
                  </span>
                  <span className="text-xs text-gray-500">
                    {task.creator} &rarr; {task.assignee}
                  </span>
                </div>
                <p className="text-sm text-gray-300 truncate">
                  {task.subject || '(no subject)'}
                </p>
              </div>
              <span className="text-xs text-gray-500 whitespace-nowrap">{formatDate(task.created_at)}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
