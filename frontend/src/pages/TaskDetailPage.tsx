import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { getTask, killTask } from '../api/mailbox';
import KillConfirmModal from '../components/KillConfirmModal';
import MorselPanel from '../components/MorselPanel';
import type { TaskDetail, FeedMessage, TaskEvent } from '../types/mailbox';

const POLL_INTERVAL_MS = 5000;
const ACTIVE_STATUSES = new Set(['pending', 'launched', 'in_progress']);

const statusColors: Record<string, string> = {
  pending: 'bg-gray-500/20 text-gray-300',
  launched: 'bg-blue-500/20 text-blue-300',
  in_progress: 'bg-amber-500/20 text-amber-300',
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
  killed: 'bg-orange-500/20 text-orange-300',
};

const senderColors: Record<string, string> = {
  ian: 'bg-purple-500/20 text-purple-300',
  doot: 'bg-indigo-500/20 text-indigo-300',
  oppy: 'bg-emerald-500/20 text-emerald-300',
  jerry: 'bg-amber-500/20 text-amber-300',
};

const toolIcons: Record<string, string> = {
  Bash: '$ ',
  Edit: '~ ',
  Write: '+ ',
  Task: '> ',
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

interface TimelineItem {
  type: 'event' | 'message' | 'tool';
  timestamp: string;
  label?: string;
  message?: FeedMessage;
  toolEvent?: TaskEvent;
}

interface ToolGroup {
  events: TaskEvent[];
  startTime: string;
  endTime: string;
}

interface TimelineEntry {
  type: 'event' | 'message' | 'tool-group';
  timestamp: string;
  label?: string;
  message?: FeedMessage;
  toolGroup?: ToolGroup;
  groupIndex?: number;
}

function buildTimeline(task: TaskDetail): TimelineItem[] {
  const items: TimelineItem[] = [];

  items.push({ type: 'event', timestamp: task.created_at, label: 'Task created' });
  if (task.started_at) {
    items.push({ type: 'event', timestamp: task.started_at, label: 'Task started' });
  }
  if (task.completed_at) {
    const verb = task.status === 'failed' ? 'Task failed' : task.status === 'killed' ? 'Task killed' : 'Task completed';
    items.push({ type: 'event', timestamp: task.completed_at, label: verb });
  }

  for (const msg of task.messages) {
    items.push({ type: 'message', timestamp: msg.created_at, message: msg });
  }

  for (const ev of (task.events || [])) {
    items.push({ type: 'tool', timestamp: ev.created_at, toolEvent: ev });
  }

  items.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  return items;
}

function groupToolEvents(timeline: TimelineItem[]): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  let currentToolRun: TaskEvent[] = [];
  let groupCounter = 0;

  const flushToolRun = () => {
    if (currentToolRun.length === 0) return;
    entries.push({
      type: 'tool-group',
      timestamp: currentToolRun[0].created_at,
      toolGroup: {
        events: [...currentToolRun],
        startTime: currentToolRun[0].created_at,
        endTime: currentToolRun[currentToolRun.length - 1].created_at,
      },
      groupIndex: groupCounter++,
    });
    currentToolRun = [];
  };

  for (const item of timeline) {
    if (item.type === 'tool' && item.toolEvent) {
      currentToolRun.push(item.toolEvent);
    } else {
      flushToolRun();
      entries.push({
        type: item.type as 'event' | 'message',
        timestamp: item.timestamp,
        label: item.label,
        message: item.message,
      });
    }
  }
  flushToolRun();

  return entries;
}

function buildToolGroupSummary(events: TaskEvent[]): string {
  const counts: Record<string, number> = {};
  for (const ev of events) {
    const name = ev.tool_name || 'Unknown';
    counts[name] = (counts[name] || 0) + 1;
  }
  const parts = Object.entries(counts).map(([name, count]) => `${count}\u00d7 ${name}`);
  return `${events.length} tool use${events.length === 1 ? '' : 's'} \u2014 ${parts.join(', ')}`;
}

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [newestFirst, setNewestFirst] = useState(false);
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [showTools, setShowTools] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [showKillModal, setShowKillModal] = useState(false);
  const [killLoading, setKillLoading] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchTask = useCallback(async () => {
    if (!id) return;
    try {
      const data = await getTask(Number(id));
      setTask(data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
    }
  }, [id]);

  // Initial load
  useEffect(() => {
    setLoading(true);
    fetchTask().finally(() => setLoading(false));
  }, [fetchTask]);

  // Auto-poll while task is active
  useEffect(() => {
    if (task && ACTIVE_STATUSES.has(task.status)) {
      intervalRef.current = setInterval(fetchTask, POLL_INTERVAL_MS);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [task?.status, fetchTask]);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!task) return <p className="text-gray-500">Task not found.</p>;

  const rawTimeline = buildTimeline(task);
  if (newestFirst) rawTimeline.reverse();
  const timeline = groupToolEvents(rawTimeline);

  const isActive = ACTIVE_STATUSES.has(task.status);
  const eventCount = (task.events || []).length;

  const toggleGroup = (groupIndex: number) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(groupIndex)) {
        next.delete(groupIndex);
      } else {
        next.add(groupIndex);
      }
      return next;
    });
  };

  const handleToggleTools = () => {
    if (showTools) {
      setExpandedGroups(new Set());
    }
    setShowTools(!showTools);
  };

  const handleKill = async () => {
    setKillLoading(true);
    try {
      await killTask(task.id);
      await fetchTask();
    } catch {
      // Refetch anyway to show latest state
      await fetchTask();
    } finally {
      setKillLoading(false);
      setShowKillModal(false);
    }
  };

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
              <span className="text-xs font-mono text-gray-500">#{task.id}</span>
              <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${statusColors[task.status] || 'bg-gray-700 text-gray-300'}`}>
                {task.status}
              </span>
              {isActive && (
                <>
                  <span className="inline-flex items-center gap-1 text-xs text-blue-400">
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
                    live
                  </span>
                  <button
                    onClick={() => setShowKillModal(true)}
                    className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-orange-500/20 text-orange-300 hover:bg-orange-500/30 transition-colors"
                  >
                    Kill
                  </button>
                </>
              )}
              <span className="text-xs text-gray-500">
                {task.creator} &rarr; {task.assignee}
              </span>
            </div>
            <h1 className="text-xl font-semibold text-gray-100">
              {task.subject || '(no subject)'}
            </h1>
            {(task.parent_task_id || task.root_task_id || (task.children && task.children.length > 0) || (task.linked_cards && task.linked_cards.length > 0)) && (
              <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                {task.parent_task_id && (
                  <Link to={`/tasks/${task.parent_task_id}`} className="text-xs text-indigo-400 hover:text-indigo-300">
                    Parent: #{task.parent_task_id}
                  </Link>
                )}
                {task.root_task_id && task.root_task_id !== task.id && (
                  <Link to={`/trees/${task.root_task_id}`} className="text-xs text-indigo-400 hover:text-indigo-300">
                    Tree: #{task.root_task_id}
                  </Link>
                )}
                {task.children && task.children.length > 0 && (
                  <span className="text-xs text-gray-500">Children: {task.children.length}</span>
                )}
                {task.linked_cards && task.linked_cards.map(card => (
                  <Link
                    key={card.id}
                    to={`/board?card=${card.id}`}
                    className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 transition-colors"
                  >
                    Card #{card.id}: {card.title}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-gray-500">
          <span>Created: {formatDate(task.created_at)}</span>
          {task.started_at && <span>Started: {formatDate(task.started_at)}</span>}
          {task.completed_at && <span>Completed: {formatDate(task.completed_at)}</span>}
        </div>
      </div>

      {/* Prompt */}
      <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-4">
        <button
          onClick={() => setPromptExpanded(!promptExpanded)}
          className="flex items-center gap-2 text-sm font-medium text-gray-300 hover:text-gray-100 transition-colors w-full text-left"
        >
          <span className={`transition-transform ${promptExpanded ? 'rotate-90' : ''}`}>&#9654;</span>
          Prompt
        </button>
        {promptExpanded && (
          <pre className="mt-3 text-sm text-gray-400 whitespace-pre-wrap overflow-x-auto">{task.prompt}</pre>
        )}
      </div>

      {/* Output */}
      {task.output && (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-4">
          <p className="text-sm font-medium text-gray-300 mb-2">Output</p>
          <pre className="text-sm text-gray-400 whitespace-pre-wrap overflow-x-auto">{task.output}</pre>
        </div>
      )}

      {/* On Complete */}
      {task.on_complete && (
        <div className="rounded-xl border border-indigo-700/50 bg-indigo-950/20 p-4 mb-4">
          <p className="text-sm font-medium text-indigo-300 mb-2">On Complete Instructions</p>
          <pre className="text-sm text-gray-400 whitespace-pre-wrap overflow-x-auto">{task.on_complete}</pre>
        </div>
      )}

      {/* Morsels */}
      <MorselPanel objectType="task" objectId={task.id} />

      {/* Timeline */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-200">Timeline</h2>
        <div className="flex items-center gap-2">
          {eventCount > 0 && (
            <button
              onClick={handleToggleTools}
              className="text-xs text-gray-400 hover:text-gray-200 border border-gray-700 rounded px-2 py-1 transition-colors"
            >
              {showTools ? 'Hide' : 'Show'} tool events ({eventCount})
            </button>
          )}
          <button
            onClick={() => setNewestFirst(!newestFirst)}
            className="text-xs text-gray-400 hover:text-gray-200 border border-gray-700 rounded px-2 py-1 transition-colors"
          >
            {newestFirst ? 'Newest first' : 'Oldest first'}
          </button>
        </div>
      </div>

      <div className="space-y-1">
        {timeline.map((entry, i) => {
          if (entry.type === 'tool-group' && !showTools) return null;

          if (entry.type === 'event') {
            return (
              <div key={`ev-${i}`} className="flex items-center gap-3 py-2">
                <div className="h-2 w-2 rounded-full bg-gray-600 shrink-0" />
                <span className="text-sm text-gray-400">{entry.label}</span>
                <span className="text-xs text-gray-600">{formatDate(entry.timestamp)}</span>
              </div>
            );
          }

          if (entry.type === 'tool-group' && entry.toolGroup) {
            const group = entry.toolGroup;
            const gIdx = entry.groupIndex!;

            // Single-event groups render inline without expand/collapse
            if (group.events.length === 1) {
              const ev = group.events[0];
              const icon = (ev.tool_name && toolIcons[ev.tool_name]) || '';
              return (
                <div key={`tg-${gIdx}`} className="flex items-center gap-3 py-1 pl-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-cyan-700 shrink-0" />
                  <span className="text-xs font-mono text-cyan-600">
                    {icon}{ev.summary}
                  </span>
                  <span className="text-xs text-gray-700">{formatTime(ev.created_at)}</span>
                </div>
              );
            }

            // Multi-event groups: collapsible cluster
            const isExpanded = expandedGroups.has(gIdx);
            return (
              <div key={`tg-${gIdx}`}>
                <button
                  onClick={() => toggleGroup(gIdx)}
                  className="flex items-center gap-3 py-1.5 pl-1 w-full text-left hover:bg-gray-800/30 rounded transition-colors group"
                >
                  <div className="h-1.5 w-1.5 rounded-full bg-cyan-700 shrink-0" />
                  <span className={`text-xs text-cyan-700 transition-transform ${isExpanded ? 'rotate-90' : ''}`}>&#9654;</span>
                  <span className="text-xs text-cyan-700 group-hover:text-cyan-500 transition-colors">
                    {buildToolGroupSummary(group.events)}
                  </span>
                  <span className="text-xs text-gray-700">
                    {formatTime(group.startTime)}{group.startTime !== group.endTime && ` \u2013 ${formatTime(group.endTime)}`}
                  </span>
                </button>
                {isExpanded && (
                  <div className="ml-6 border-l border-cyan-900/30 pl-3 space-y-0.5">
                    {group.events.map(ev => {
                      const icon = (ev.tool_name && toolIcons[ev.tool_name]) || '';
                      return (
                        <div key={`tool-${ev.id}`} className="flex items-center gap-3 py-0.5">
                          <div className="h-1 w-1 rounded-full bg-cyan-800 shrink-0" />
                          <span className="text-xs font-mono text-cyan-700">
                            {icon}{ev.summary}
                          </span>
                          <span className="text-xs text-gray-700">{formatTime(ev.created_at)}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          }

          if (entry.type === 'message' && entry.message) {
            return (
              <Link
                key={`msg-${entry.message.id}`}
                to={`/messages/${entry.message.id}`}
                className="block rounded-lg border border-gray-800 p-4 transition-colors hover:bg-gray-800/50"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-gray-500">#{entry.message.id}</span>
                      <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${senderColors[entry.message.sender] || 'bg-gray-700 text-gray-300'}`}>
                        {entry.message.sender}
                      </span>
                      <span className="text-xs text-gray-500">
                        to {entry.message.recipients.join(', ')}
                      </span>
                    </div>
                    <p className="text-sm text-gray-300 truncate">
                      {entry.message.subject || '(no subject)'}
                    </p>
                    <p className="text-xs text-gray-500 truncate mt-0.5">{entry.message.body}</p>
                  </div>
                  <span className="text-xs text-gray-500 whitespace-nowrap">{formatDate(entry.message.created_at)}</span>
                </div>
              </Link>
            );
          }

          return null;
        })}
        {timeline.length === 0 && (
          <p className="text-gray-500 text-sm">No timeline events.</p>
        )}
      </div>

      <KillConfirmModal
        open={showKillModal}
        subject={task.subject}
        onConfirm={handleKill}
        onCancel={() => setShowKillModal(false)}
        loading={killLoading}
      />
    </div>
  );
}
