import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { getCard, updateCard, deleteCard, getTask } from '../api/mailbox';
import Linkify from '../components/Linkify';
import MorselPanel from '../components/MorselPanel';
import PeekDrawer from '../components/PeekDrawer';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { parseGitHubPrLink } from '../utils/links';
import type { CardSummary, TaskSummary } from '../types/mailbox';

const COLUMNS = ['backlog', 'todo', 'in_progress', 'done'] as const;
const PRIORITIES = ['low', 'normal', 'high', 'urgent'] as const;

const COLUMN_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  todo: 'To Do',
  in_progress: 'In Progress',
  done: 'Done',
  archived: 'Archived',
};

const COLUMN_COLORS: Record<string, string> = {
  backlog: 'bg-gray-600 text-gray-200',
  todo: 'bg-blue-600 text-blue-100',
  in_progress: 'bg-amber-600 text-amber-100',
  done: 'bg-emerald-600 text-emerald-100',
  archived: 'bg-gray-700 text-gray-400',
};

const PRIORITY_COLORS: Record<string, string> = {
  urgent: 'bg-red-600 text-white',
  high: 'bg-orange-600 text-white',
  normal: 'bg-gray-600 text-gray-200',
  low: 'bg-gray-700 text-gray-400',
};

const TASK_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-500/20 text-gray-300',
  launched: 'bg-blue-500/20 text-blue-300',
  in_progress: 'bg-amber-500/20 text-amber-300',
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
  killed: 'bg-orange-500/20 text-orange-300',
};

const linkColorMap: Record<string, string> = {
  task: 'bg-indigo-900/50 text-indigo-300 hover:bg-indigo-900',
  morsel: 'bg-amber-900/50 text-amber-300 hover:bg-amber-900',
  tree: 'bg-cyan-900/50 text-cyan-300 hover:bg-cyan-900',
  message: 'bg-purple-900/50 text-purple-300 hover:bg-purple-900',
  card: 'bg-emerald-900/50 text-emerald-300 hover:bg-emerald-900',
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

export default function CardDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [card, setCard] = useState<CardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);

  // Edit form state
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editPriority, setEditPriority] = useState('');
  const [editAssignee, setEditAssignee] = useState('');
  const [editLabels, setEditLabels] = useState('');
  const [editProject, setEditProject] = useState('');

  // Linked task statuses
  const [linkedTasks, setLinkedTasks] = useState<Record<string, TaskSummary>>({});

  // Peek drawer
  const [peekObject, setPeekObject] = useState<{ type: string; id: string } | null>(null);

  useDocumentTitle(card ? `Card #${card.id} \u2013 ${card.title}` : undefined);

  const fetchCard = useCallback(async () => {
    if (!id) return;
    try {
      const data = await getCard(Number(id));
      setCard(data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    fetchCard().finally(() => setLoading(false));
  }, [fetchCard]);

  // Fetch linked task details
  useEffect(() => {
    if (!card) {
      setLinkedTasks({});
      return;
    }
    const taskLinks = card.links.filter(l => l.object_type === 'task');
    if (taskLinks.length === 0) return;
    (async () => {
      const results: Record<string, TaskSummary> = {};
      for (const link of taskLinks) {
        try {
          const task = await getTask(Number(link.object_id));
          results[link.object_id] = task;
        } catch {
          // ignore
        }
      }
      setLinkedTasks(results);
    })();
  }, [card?.id]);

  const openEdit = (c: CardSummary) => {
    setEditTitle(c.title);
    setEditDescription(c.description);
    setEditPriority(c.priority);
    setEditAssignee(c.assignee || '');
    setEditLabels(c.labels.join(', '));
    setEditProject(c.project || '');
    setEditing(true);
  };

  const handleEditSave = async () => {
    if (!card) return;
    try {
      const updated = await updateCard(card.id, {
        title: editTitle,
        description: editDescription,
        priority: editPriority,
        assignee: editAssignee.trim() || null,
        labels: editLabels.trim() ? editLabels.split(',').map(l => l.trim()).filter(Boolean) : [],
        project: editProject.trim() || null,
      });
      setCard(updated);
      setEditing(false);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
    }
  };

  const handleMove = async (toCol: string) => {
    if (!card) return;
    try {
      const updated = await updateCard(card.id, { col: toCol });
      setCard(updated);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
    }
  };

  const handleDelete = async () => {
    if (!card) return;
    if (!confirm('Delete this card?')) return;
    await deleteCard(card.id);
    navigate('/board');
  };

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!card) return <p className="text-gray-500">Card not found.</p>;

  const taskLinks = card.links.filter(l => l.object_type === 'task');
  const ghPrLinks = card.links.filter(l => l.object_type === 'github_pr');
  const otherLinks = card.links.filter(l => l.object_type !== 'task' && l.object_type !== 'github_pr');

  return (
    <div>
      <button onClick={() => navigate(-1)} className="text-sm text-gray-400 hover:text-gray-200 mb-4 inline-block">
        &larr; Back
      </button>

      {editing ? (
        /* Edit form */
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-6 mb-4">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Edit Card</h2>
          <div className="space-y-3">
            <input
              type="text"
              value={editTitle}
              onChange={e => setEditTitle(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100"
              placeholder="Title"
            />
            <textarea
              value={editDescription}
              onChange={e => setEditDescription(e.target.value)}
              rows={6}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100"
              placeholder="Description"
            />
            <div className="flex gap-2 flex-wrap">
              <select
                value={editPriority}
                onChange={e => setEditPriority(e.target.value)}
                className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200"
              >
                {PRIORITIES.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              <input
                type="text"
                placeholder="Assignee"
                value={editAssignee}
                onChange={e => setEditAssignee(e.target.value)}
                className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500"
              />
              <input
                type="text"
                placeholder="Project"
                value={editProject}
                onChange={e => setEditProject(e.target.value)}
                className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500"
              />
              <input
                type="text"
                placeholder="Labels (comma-separated)"
                value={editLabels}
                onChange={e => setEditLabels(e.target.value)}
                className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500 flex-1"
              />
            </div>
            <div className="flex gap-2">
              <button onClick={handleEditSave} className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-500">
                Save
              </button>
              <button onClick={() => setEditing(false)} className="px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded hover:bg-gray-600">
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* Header */}
          <div className="rounded-xl border border-gray-700 bg-gray-900 p-6 mb-4">
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-mono text-gray-500">#{card.id}</span>
                  <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${COLUMN_COLORS[card.col] || 'bg-gray-700 text-gray-300'}`}>
                    {COLUMN_LABELS[card.col] || card.col}
                  </span>
                  <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${PRIORITY_COLORS[card.priority]}`}>
                    {card.priority}
                  </span>
                  {card.project && (
                    <span className="px-2 py-0.5 rounded text-xs bg-teal-900 text-teal-300">
                      {card.project}
                    </span>
                  )}
                  {card.assignee && (
                    <span className="px-2 py-0.5 rounded text-xs bg-indigo-900 text-indigo-300">
                      @{card.assignee}
                    </span>
                  )}
                </div>
                <h1 className="text-xl font-semibold text-gray-100">{card.title}</h1>
              </div>
            </div>

            {/* Labels */}
            {card.labels.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-3">
                {card.labels.map(l => (
                  <span key={l} className="px-2 py-0.5 rounded text-xs bg-gray-700 text-gray-300">{l}</span>
                ))}
              </div>
            )}

            {/* Metadata */}
            <div className="flex flex-wrap gap-4 text-xs text-gray-500">
              <span>Creator: {card.creator}</span>
              <span>Created: {formatDate(card.created_at)}</span>
              <span>Updated: {formatDate(card.updated_at)}</span>
            </div>
          </div>

          {/* Description */}
          {card.description && (
            <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-4">
              <p className="text-sm font-medium text-gray-300 mb-2">Description</p>
              <div className="text-sm text-gray-400 whitespace-pre-wrap"><Linkify>{card.description}</Linkify></div>
            </div>
          )}

          {/* Links */}
          {(taskLinks.length > 0 || ghPrLinks.length > 0 || otherLinks.length > 0) && (
            <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-4">
              <p className="text-sm font-medium text-gray-300 mb-3">Links</p>

              {/* Task links with status */}
              {taskLinks.length > 0 && (
                <div className="mb-3">
                  <div className="text-xs text-gray-500 mb-1.5">Tasks</div>
                  <div className="space-y-1">
                    {taskLinks.map((link, i) => {
                      const task = linkedTasks[link.object_id];
                      return (
                        <div key={`task-${link.object_id}-${i}`} className="flex items-center gap-2">
                          <button
                            onClick={() => setPeekObject({ type: 'task', id: link.object_id })}
                            className="text-xs font-medium text-indigo-300 hover:text-indigo-200 transition-colors"
                          >
                            Task #{link.object_id}
                          </button>
                          {task && (
                            <>
                              <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${TASK_STATUS_COLORS[task.status] || 'bg-gray-700 text-gray-300'}`}>
                                {task.status}
                              </span>
                              <span className="text-xs text-gray-500 truncate">{task.subject}</span>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* GitHub PR links */}
              {ghPrLinks.length > 0 && (
                <div className="mb-3">
                  <div className="text-xs text-gray-500 mb-1.5">Pull Requests</div>
                  <div className="flex flex-wrap gap-1.5">
                    {ghPrLinks.map((link, i) => {
                      const parsed = parseGitHubPrLink(link.object_id);
                      if (!parsed) return null;
                      return (
                        <button
                          key={`gh-pr-${link.object_id}-${i}`}
                          onClick={() => window.open(parsed.url, '_blank')}
                          className="px-2 py-0.5 rounded text-xs font-medium transition-colors cursor-pointer bg-gray-800 text-gray-100 hover:bg-gray-700 border border-gray-600"
                        >
                          {parsed.label} ↗
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Other links */}
              {otherLinks.length > 0 && (
                <div>
                  <div className="text-xs text-gray-500 mb-1.5">Linked</div>
                  <div className="flex flex-wrap gap-1.5">
                    {otherLinks.map((link, i) => {
                      const key = `${link.object_type}-${link.object_id}-${i}`;
                      const label = `${link.object_type} #${link.object_id}`;
                      const colors = linkColorMap[link.object_type] || 'bg-gray-700 text-gray-300';
                      return (
                        <button
                          key={key}
                          onClick={() => setPeekObject({ type: link.object_type, id: link.object_id })}
                          className={`px-2 py-0.5 rounded text-xs font-medium transition-colors cursor-pointer ${colors}`}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Morsels */}
          <MorselPanel objectType="card" objectId={card.id} />

          {/* Actions */}
          <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-4">
            <div className="flex items-center gap-2 flex-wrap">
              <button onClick={() => openEdit(card)} className="px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded hover:bg-gray-600">
                Edit
              </button>

              {/* Move buttons */}
              {card.col !== 'archived' && (
                <>
                  <span className="text-xs text-gray-500">Move to:</span>
                  {COLUMNS.filter(c => c !== card.col).map(col => (
                    <button
                      key={col}
                      onClick={() => handleMove(col)}
                      className="px-2 py-1 text-xs bg-gray-800 text-gray-300 rounded hover:bg-gray-700 border border-gray-700"
                    >
                      {COLUMN_LABELS[col]}
                    </button>
                  ))}
                </>
              )}
              {card.col === 'archived' && (
                <>
                  <span className="text-xs text-gray-500">Move to:</span>
                  {COLUMNS.map(col => (
                    <button
                      key={col}
                      onClick={() => handleMove(col)}
                      className="px-2 py-1 text-xs bg-gray-800 text-gray-300 rounded hover:bg-gray-700 border border-gray-700"
                    >
                      {COLUMN_LABELS[col]}
                    </button>
                  ))}
                </>
              )}

              {card.col !== 'archived' && (
                <button onClick={() => handleMove('archived')} className="px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded hover:bg-gray-600">
                  Archive
                </button>
              )}
              <button onClick={handleDelete} className="px-3 py-1.5 bg-red-900 text-red-300 text-sm rounded hover:bg-red-800 ml-auto">
                Delete
              </button>
            </div>
          </div>
        </>
      )}

      {/* Peek drawer */}
      <PeekDrawer
        open={!!peekObject}
        onClose={() => setPeekObject(null)}
        objectType={peekObject?.type || ''}
        objectId={peekObject?.id || ''}
      />
    </div>
  );
}
