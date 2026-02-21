import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { getThrum } from '../api/mailbox';
import MorselPanel from '../components/MorselPanel';
import type { ThrumDetail } from '../types/mailbox';

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

const taskStatusColors: Record<string, string> = {
  pending: 'bg-gray-500/20 text-gray-300',
  launched: 'bg-blue-500/20 text-blue-300',
  in_progress: 'bg-amber-500/20 text-amber-300',
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

export default function ThrumDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [thrum, setThrum] = useState<ThrumDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [planExpanded, setPlanExpanded] = useState(true);

  const fetchThrum = useCallback(async () => {
    if (!id) return;
    try {
      const data = await getThrum(Number(id));
      setThrum(data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    fetchThrum().finally(() => setLoading(false));
  }, [fetchThrum]);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!thrum) return <p className="text-gray-500">Thrum not found.</p>;

  return (
    <div>
      <button onClick={() => navigate(-1)} className="text-sm text-gray-400 hover:text-gray-200 mb-4 inline-block">
        &larr; Back
      </button>

      {/* Header */}
      <div className="rounded-xl border border-gray-700 bg-gray-900 p-6 mb-4">
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-mono text-gray-500">#{thrum.id}</span>
              <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${statusColors[thrum.status] || 'bg-gray-700 text-gray-300'}`}>
                {thrum.status}
              </span>
              <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${priorityColors[thrum.priority] || 'bg-gray-700 text-gray-300'}`}>
                {thrum.priority}
              </span>
              <span className="text-xs text-gray-500">{thrum.creator}</span>
            </div>
            <h1 className="text-xl font-semibold text-gray-100">
              {thrum.title || '(no title)'}
            </h1>
            {thrum.goal && (
              <p className="text-sm text-gray-400 mt-1">{thrum.goal}</p>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-gray-500">
          <span>Created: {formatDate(thrum.created_at)}</span>
          {thrum.started_at && <span>Started: {formatDate(thrum.started_at)}</span>}
          {thrum.completed_at && <span>Completed: {formatDate(thrum.completed_at)}</span>}
        </div>
      </div>

      {/* Plan */}
      {thrum.plan && (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-4">
          <button
            onClick={() => setPlanExpanded(!planExpanded)}
            className="flex items-center gap-2 text-sm font-medium text-gray-300 hover:text-gray-100 transition-colors w-full text-left"
          >
            <span className={`transition-transform ${planExpanded ? 'rotate-90' : ''}`}>&#9654;</span>
            Plan
          </button>
          {planExpanded && (
            <pre className="mt-3 text-sm text-gray-400 whitespace-pre-wrap overflow-x-auto">{thrum.plan}</pre>
          )}
        </div>
      )}

      {/* Output */}
      {thrum.output && (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-4">
          <p className="text-sm font-medium text-gray-300 mb-2">Output</p>
          <pre className="text-sm text-gray-400 whitespace-pre-wrap overflow-x-auto">{thrum.output}</pre>
        </div>
      )}

      {/* Morsels */}
      <MorselPanel objectType="thrum" objectId={thrum.id} />

      {/* Linked Tasks */}
      <h2 className="text-lg font-semibold text-gray-200 mb-3">
        Linked Tasks {thrum.tasks.length > 0 && <span className="text-sm font-normal text-gray-500">({thrum.tasks.length})</span>}
      </h2>
      {thrum.tasks.length === 0 ? (
        <p className="text-gray-500 text-sm">No linked tasks.</p>
      ) : (
        <div className="space-y-2">
          {thrum.tasks.map((task) => (
            <Link
              key={task.id}
              to={`/tasks/${task.id}`}
              className="block rounded-lg border border-gray-800 p-4 transition-colors hover:bg-gray-800/50"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono text-gray-500">#{task.id}</span>
                    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${taskStatusColors[task.status] || 'bg-gray-700 text-gray-300'}`}>
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
                <span className="text-xs text-gray-500 whitespace-nowrap">
                  {formatDate(task.created_at)}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
