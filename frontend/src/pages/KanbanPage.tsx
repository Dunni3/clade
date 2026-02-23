import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getCards, createCard, updateCard, deleteCard, getTask } from '../api/mailbox';
import type { CardSummary, CreateCardRequest, TaskSummary } from '../types/mailbox';
import Linkify from '../components/Linkify';
import PeekDrawer from '../components/PeekDrawer';

const COLUMNS = ['backlog', 'todo', 'in_progress', 'done'] as const;
const ALL_COLUMNS = ['backlog', 'todo', 'in_progress', 'done', 'archived'] as const;
const PRIORITIES = ['low', 'normal', 'high', 'urgent'] as const;

const COLUMN_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  todo: 'To Do',
  in_progress: 'In Progress',
  done: 'Done',
  archived: 'Archived',
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

function getAdjacentColumns(col: string): { prev: string | null; next: string | null } {
  const idx = COLUMNS.indexOf(col as typeof COLUMNS[number]);
  return {
    prev: idx > 0 ? COLUMNS[idx - 1] : null,
    next: idx < COLUMNS.length - 1 ? COLUMNS[idx + 1] : null,
  };
}

export default function KanbanPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [cards, setCards] = useState<CardSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedCard, setSelectedCard] = useState<CardSummary | null>(null);
  const [editingCard, setEditingCard] = useState(false);

  // Filters
  const [filterAssignee, setFilterAssignee] = useState('');
  const [filterLabel, setFilterLabel] = useState('');
  const [filterPriority, setFilterPriority] = useState('');
  const [filterProject, setFilterProject] = useState('');

  // Create form state
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newCol, setNewCol] = useState<string>('backlog');
  const [newPriority, setNewPriority] = useState<string>('normal');
  const [newAssignee, setNewAssignee] = useState('');
  const [newLabels, setNewLabels] = useState('');
  const [newProject, setNewProject] = useState('');

  // Peek drawer state
  const [peekObject, setPeekObject] = useState<{ type: string; id: string } | null>(null);

  // Linked task statuses (for card detail modal)
  const [linkedTasks, setLinkedTasks] = useState<Record<string, TaskSummary>>({});

  // Edit form state
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editPriority, setEditPriority] = useState('');
  const [editAssignee, setEditAssignee] = useState('');
  const [editLabels, setEditLabels] = useState('');
  const [editProject, setEditProject] = useState('');

  const fetchCards = async () => {
    try {
      const data = await getCards({
        include_archived: showArchived,
        assignee: filterAssignee || undefined,
        label: filterLabel || undefined,
        priority: filterPriority || undefined,
        project: filterProject || undefined,
      });
      setCards(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCards();
  }, [showArchived, filterAssignee, filterLabel, filterPriority, filterProject]);

  // Fetch linked task details when a card is selected
  useEffect(() => {
    if (!selectedCard) {
      setLinkedTasks({});
      return;
    }
    const taskLinks = selectedCard.links.filter(l => l.object_type === 'task');
    if (taskLinks.length === 0) return;
    (async () => {
      const results: Record<string, TaskSummary> = {};
      for (const link of taskLinks) {
        try {
          const task = await getTask(Number(link.object_id));
          results[link.object_id] = task;
        } catch {
          // ignore fetch failures
        }
      }
      setLinkedTasks(results);
    })();
  }, [selectedCard?.id]);

  // Auto-open card from ?card=N query param
  useEffect(() => {
    const cardParam = searchParams.get('card');
    if (cardParam && cards.length > 0) {
      const cardId = parseInt(cardParam, 10);
      const found = cards.find(c => c.id === cardId);
      if (found) {
        setSelectedCard(found);
        setEditingCard(false);
        setSearchParams({}, { replace: true });
      }
    }
  }, [cards, searchParams]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    const req: CreateCardRequest = {
      title: newTitle.trim(),
      description: newDescription.trim(),
      col: newCol,
      priority: newPriority,
      assignee: newAssignee.trim() || undefined,
      labels: newLabels.trim() ? newLabels.split(',').map(l => l.trim()).filter(Boolean) : undefined,
      project: newProject.trim() || undefined,
    };
    await createCard(req);
    setNewTitle('');
    setNewDescription('');
    setNewCol('backlog');
    setNewPriority('normal');
    setNewAssignee('');
    setNewLabels('');
    setNewProject('');
    setShowCreateForm(false);
    fetchCards();
  };

  const handleMove = async (cardId: number, toCol: string) => {
    await updateCard(cardId, { col: toCol });
    if (selectedCard?.id === cardId) {
      setSelectedCard({ ...selectedCard, col: toCol });
    }
    fetchCards();
  };

  const handleDelete = async (cardId: number) => {
    if (!confirm('Delete this card?')) return;
    await deleteCard(cardId);
    setSelectedCard(null);
    fetchCards();
  };

  const handleEditSave = async () => {
    if (!selectedCard) return;
    await updateCard(selectedCard.id, {
      title: editTitle,
      description: editDescription,
      priority: editPriority,
      assignee: editAssignee.trim() || null,
      labels: editLabels.trim() ? editLabels.split(',').map(l => l.trim()).filter(Boolean) : [],
      project: editProject.trim() || null,
    });
    setEditingCard(false);
    setSelectedCard(null);
    fetchCards();
  };

  const openEdit = (card: CardSummary) => {
    setEditTitle(card.title);
    setEditDescription(card.description);
    setEditPriority(card.priority);
    setEditAssignee(card.assignee || '');
    setEditLabels(card.labels.join(', '));
    setEditProject(card.project || '');
    setEditingCard(true);
  };

  const columnsToShow = showArchived ? ALL_COLUMNS : COLUMNS;

  const cardsByCol = (col: string) => cards.filter(c => c.col === col);

  if (loading) {
    return <div className="text-gray-400">Loading board...</div>;
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-gray-100">Board</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-500"
          >
            + New Card
          </button>
          <label className="flex items-center gap-1.5 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={e => setShowArchived(e.target.checked)}
              className="rounded"
            />
            Archived
          </label>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        <input
          type="text"
          placeholder="Filter project..."
          value={filterProject}
          onChange={e => setFilterProject(e.target.value)}
          className="px-2 py-1 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500"
        />
        <input
          type="text"
          placeholder="Filter assignee..."
          value={filterAssignee}
          onChange={e => setFilterAssignee(e.target.value)}
          className="px-2 py-1 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500"
        />
        <input
          type="text"
          placeholder="Filter label..."
          value={filterLabel}
          onChange={e => setFilterLabel(e.target.value)}
          className="px-2 py-1 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500"
        />
        <select
          value={filterPriority}
          onChange={e => setFilterPriority(e.target.value)}
          className="px-2 py-1 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200"
        >
          <option value="">All priorities</option>
          {PRIORITIES.map(p => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>

      {/* Create form */}
      {showCreateForm && (
        <form onSubmit={handleCreate} className="mb-4 p-4 bg-gray-900 border border-gray-700 rounded space-y-2">
          <input
            type="text"
            placeholder="Title *"
            value={newTitle}
            onChange={e => setNewTitle(e.target.value)}
            required
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 placeholder-gray-500"
          />
          <textarea
            placeholder="Description"
            value={newDescription}
            onChange={e => setNewDescription(e.target.value)}
            rows={2}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 placeholder-gray-500"
          />
          <div className="flex gap-2">
            <select
              value={newCol}
              onChange={e => setNewCol(e.target.value)}
              className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200"
            >
              {ALL_COLUMNS.map(c => (
                <option key={c} value={c}>{COLUMN_LABELS[c]}</option>
              ))}
            </select>
            <select
              value={newPriority}
              onChange={e => setNewPriority(e.target.value)}
              className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200"
            >
              {PRIORITIES.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Assignee"
              value={newAssignee}
              onChange={e => setNewAssignee(e.target.value)}
              className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500"
            />
            <input
              type="text"
              placeholder="Project"
              value={newProject}
              onChange={e => setNewProject(e.target.value)}
              className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500"
            />
            <input
              type="text"
              placeholder="Labels (comma-separated)"
              value={newLabels}
              onChange={e => setNewLabels(e.target.value)}
              className="px-2 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500 flex-1"
            />
          </div>
          <div className="flex gap-2">
            <button type="submit" className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-500">
              Create
            </button>
            <button type="button" onClick={() => setShowCreateForm(false)} className="px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded hover:bg-gray-600">
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Board columns */}
      <div className="flex gap-3 overflow-x-auto pb-4" style={{ minHeight: '400px' }}>
        {columnsToShow.map(col => {
          const colCards = cardsByCol(col);
          return (
            <div key={col} className="flex-shrink-0 w-64 bg-gray-900 border border-gray-800 rounded">
              <div className="px-3 py-2 border-b border-gray-800">
                <h2 className="text-sm font-semibold text-gray-300">
                  {COLUMN_LABELS[col]} <span className="text-gray-500">({colCards.length})</span>
                </h2>
              </div>
              <div className="p-2 space-y-2 max-h-[calc(100vh-320px)] overflow-y-auto">
                {colCards.map(card => {
                  const { prev, next } = getAdjacentColumns(card.col);
                  return (
                    <div
                      key={card.id}
                      className="p-2.5 bg-gray-800 border border-gray-700 rounded cursor-pointer hover:border-gray-600 transition-colors"
                      onClick={() => { setSelectedCard(card); setEditingCard(false); }}
                    >
                      <div className="flex items-start justify-between gap-1">
                        <span className="text-sm font-medium text-gray-100 leading-tight">{card.title}</span>
                        <span className="text-xs text-gray-500 flex-shrink-0">#{card.id}</span>
                      </div>
                      <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                        {card.priority !== 'normal' && (
                          <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${PRIORITY_COLORS[card.priority]}`}>
                            {card.priority}
                          </span>
                        )}
                        {card.project && (
                          <span className="px-1.5 py-0.5 rounded text-xs bg-teal-900 text-teal-300">
                            {card.project}
                          </span>
                        )}
                        {card.assignee && (
                          <span className="px-1.5 py-0.5 rounded text-xs bg-indigo-900 text-indigo-300">
                            @{card.assignee}
                          </span>
                        )}
                        {card.labels.map(l => (
                          <span key={l} className="px-1.5 py-0.5 rounded text-xs bg-gray-700 text-gray-300">
                            {l}
                          </span>
                        ))}
                      </div>
                      {/* Move buttons */}
                      {col !== 'archived' && (
                        <div className="flex justify-between mt-2">
                          <button
                            disabled={!prev}
                            onClick={e => { e.stopPropagation(); if (prev) handleMove(card.id, prev); }}
                            className={`text-xs px-1.5 py-0.5 rounded ${prev ? 'text-gray-400 hover:text-gray-200 hover:bg-gray-700' : 'text-gray-700 cursor-not-allowed'}`}
                          >
                            &larr;
                          </button>
                          <button
                            disabled={!next}
                            onClick={e => { e.stopPropagation(); if (next) handleMove(card.id, next); }}
                            className={`text-xs px-1.5 py-0.5 rounded ${next ? 'text-gray-400 hover:text-gray-200 hover:bg-gray-700' : 'text-gray-700 cursor-not-allowed'}`}
                          >
                            &rarr;
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
                {colCards.length === 0 && (
                  <div className="text-xs text-gray-600 text-center py-4">No cards</div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Detail / Edit panel */}
      {selectedCard && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedCard(null)}>
          <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-lg mx-4 p-5 max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            {editingCard ? (
              <div className="space-y-3">
                <h2 className="text-lg font-semibold text-gray-100">Edit Card</h2>
                <input
                  type="text"
                  value={editTitle}
                  onChange={e => setEditTitle(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100"
                />
                <textarea
                  value={editDescription}
                  onChange={e => setEditDescription(e.target.value)}
                  rows={3}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100"
                />
                <div className="flex gap-2">
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
                  <button onClick={() => setEditingCard(false)} className="px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded hover:bg-gray-600">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex items-start justify-between mb-3">
                  <h2 className="text-lg font-semibold text-gray-100">{selectedCard.title}</h2>
                  <span className="text-sm text-gray-500">#{selectedCard.id}</span>
                </div>
                <div className="space-y-1.5 text-sm text-gray-300 mb-3">
                  <div>Column: <span className="text-gray-100">{COLUMN_LABELS[selectedCard.col]}</span></div>
                  <div>Priority: <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${PRIORITY_COLORS[selectedCard.priority]}`}>{selectedCard.priority}</span></div>
                  <div>Creator: <span className="text-gray-100">{selectedCard.creator}</span></div>
                  {selectedCard.project && <div>Project: <span className="text-teal-400">{selectedCard.project}</span></div>}
                  {selectedCard.assignee && <div>Assignee: <span className="text-indigo-400">@{selectedCard.assignee}</span></div>}
                  {selectedCard.labels.length > 0 && (
                    <div className="flex items-center gap-1">
                      Labels: {selectedCard.labels.map(l => (
                        <span key={l} className="px-1.5 py-0.5 rounded text-xs bg-gray-700 text-gray-300">{l}</span>
                      ))}
                    </div>
                  )}
                </div>
                {selectedCard.description && (
                  <p className="text-sm text-gray-400 mb-4 whitespace-pre-wrap max-h-60 overflow-y-auto"><Linkify>{selectedCard.description}</Linkify></p>
                )}
                {selectedCard.links && selectedCard.links.length > 0 && (() => {
                  const taskLinks = selectedCard.links.filter(l => l.object_type === 'task');
                  const otherLinks = selectedCard.links.filter(l => l.object_type !== 'task');
                  return (
                    <div className="mb-4">
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
                      {/* Other links */}
                      {otherLinks.length > 0 && (
                        <div>
                          <div className="text-xs text-gray-500 mb-1.5">Linked</div>
                          <div className="flex flex-wrap gap-1.5">
                            {otherLinks.map((link, i) => {
                              const key = `${link.object_type}-${link.object_id}-${i}`;
                              const label = `${link.object_type} #${link.object_id}`;
                              const colorMap: Record<string, string> = {
                                morsel: 'bg-amber-900/50 text-amber-300 hover:bg-amber-900',
                                tree: 'bg-cyan-900/50 text-cyan-300 hover:bg-cyan-900',
                                message: 'bg-purple-900/50 text-purple-300 hover:bg-purple-900',
                                card: 'bg-emerald-900/50 text-emerald-300 hover:bg-emerald-900',
                              };
                              const colors = colorMap[link.object_type] || 'bg-gray-700 text-gray-300';
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
                  );
                })()}
                <div className="flex gap-2">
                  <button onClick={() => openEdit(selectedCard)} className="px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded hover:bg-gray-600">
                    Edit
                  </button>
                  <button onClick={() => handleMove(selectedCard.id, 'archived')} className="px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded hover:bg-gray-600">
                    Archive
                  </button>
                  <button onClick={() => handleDelete(selectedCard.id)} className="px-3 py-1.5 bg-red-900 text-red-300 text-sm rounded hover:bg-red-800">
                    Delete
                  </button>
                  <button onClick={() => setSelectedCard(null)} className="ml-auto px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded hover:bg-gray-600">
                    Close
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
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
