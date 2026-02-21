import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getHealthCheck, getMemberActivity, getEmberStatus, getTasks } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import type { MemberActivity, EmberInfo, TaskSummary } from '../types/mailbox';

const memberColors: Record<string, string> = {
  ian: 'border-purple-500',
  doot: 'border-indigo-500',
  oppy: 'border-emerald-500',
  jerry: 'border-amber-500',
  kamaji: 'border-cyan-500',
};

const taskStatusColors: Record<string, string> = {
  pending: 'bg-gray-500/20 text-gray-300',
  launched: 'bg-blue-500/20 text-blue-300',
  in_progress: 'bg-amber-500/20 text-amber-300',
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
};

function formatRelativeTime(iso: string | null): string {
  if (!iso) return 'never';
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function recencyDot(iso: string | null): string {
  if (!iso) return 'bg-gray-600';
  const diffMs = new Date().getTime() - new Date(iso).getTime();
  const diffHr = diffMs / 3600000;
  if (diffHr < 1) return 'bg-emerald-400';
  if (diffHr < 24) return 'bg-amber-400';
  return 'bg-gray-600';
}

function lastActivity(member: MemberActivity): string | null {
  const dates = [member.last_message_at, member.last_task_at].filter(Boolean) as string[];
  if (dates.length === 0) return null;
  return dates.sort().reverse()[0];
}

export default function StatusPage() {
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [members, setMembers] = useState<MemberActivity[]>([]);
  const [emberStatus, setEmberStatus] = useState<Record<string, EmberInfo>>({});
  const [activeTasks, setActiveTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const apiKey = useAuthStore((s) => s.apiKey);

  useEffect(() => {
    if (!apiKey) return;
    setLoading(true);

    Promise.allSettled([
      getHealthCheck().then(() => setHealthy(true)).catch(() => setHealthy(false)),
      getMemberActivity().then((res) => setMembers(res.members)).catch(() => {}),
      getEmberStatus().then((res) => setEmberStatus(res.embers)).catch(() => {}),
      getTasks({ status: 'in_progress', limit: 20 }).then(setActiveTasks).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, [apiKey]);

  if (!apiKey) {
    return <p className="text-gray-400">Set your API key in <a href="/settings" className="text-indigo-400 underline">Settings</a> first.</p>;
  }

  if (loading) return <p className="text-gray-500">Loading...</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Status</h1>

      {/* Hearth Health */}
      <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-6">
        <div className="flex items-center gap-3">
          <div className={`h-3 w-3 rounded-full ${healthy === true ? 'bg-emerald-400' : healthy === false ? 'bg-red-400' : 'bg-gray-600'}`} />
          <span className="text-sm font-medium text-gray-200">
            Hearth {healthy === true ? 'Online' : healthy === false ? 'Unreachable' : 'Checking...'}
          </span>
        </div>
      </div>

      {/* Members Grid */}
      <h2 className="text-lg font-semibold text-gray-200 mb-3">Members</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
        {members.map((member) => {
          const last = lastActivity(member);
          const borderColor = memberColors[member.name] || 'border-gray-600';
          return (
            <div
              key={member.name}
              className={`rounded-xl border-l-4 ${borderColor} border border-gray-700 bg-gray-900 p-4`}
            >
              <div className="flex items-center gap-2 mb-2">
                <div className={`h-2 w-2 rounded-full ${recencyDot(last)}`} />
                <span className="text-sm font-semibold text-gray-100">{member.name}</span>
                <span className="text-xs text-gray-500 ml-auto">{formatRelativeTime(last)}</span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <span className="text-gray-500">Messages sent</span>
                <span className="text-gray-300 text-right">{member.messages_sent}</span>
                <span className="text-gray-500">Active tasks</span>
                <span className="text-gray-300 text-right">{member.active_tasks}</span>
                <span className="text-gray-500">Running aspens</span>
                <span className="text-gray-300 text-right">
                  {emberStatus[member.name]
                    ? emberStatus[member.name].status === 'ok'
                      ? emberStatus[member.name].active_tasks ?? 0
                      : <span className="text-red-400" title="Ember unreachable">!</span>
                    : <span className="text-gray-600">&ndash;</span>}
                </span>
                <span className="text-gray-500">Completed</span>
                <span className="text-emerald-400 text-right">{member.completed_tasks}</span>
                <span className="text-gray-500">Failed</span>
                <span className="text-red-400 text-right">{member.failed_tasks}</span>
              </div>
            </div>
          );
        })}
        {members.length === 0 && (
          <p className="text-gray-500 text-sm col-span-full">No members found.</p>
        )}
      </div>

      {/* Active Tasks */}
      <h2 className="text-lg font-semibold text-gray-200 mb-3">
        Active Tasks {activeTasks.length > 0 && <span className="text-sm font-normal text-gray-500">({activeTasks.length})</span>}
      </h2>
      {activeTasks.length === 0 ? (
        <p className="text-gray-500 text-sm">No active tasks.</p>
      ) : (
        <div className="space-y-2">
          {activeTasks.map((task) => (
            <Link
              key={task.id}
              to={`/tasks/${task.id}`}
              className="block rounded-lg border border-gray-800 p-3 transition-colors hover:bg-gray-800/50"
            >
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-gray-500">#{task.id}</span>
                <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${taskStatusColors[task.status] || 'bg-gray-700 text-gray-300'}`}>
                  {task.status}
                </span>
                <span className="text-sm text-gray-300 truncate">{task.subject || '(no subject)'}</span>
                <span className="text-xs text-gray-500 ml-auto">
                  {task.creator} &rarr; {task.assignee}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
