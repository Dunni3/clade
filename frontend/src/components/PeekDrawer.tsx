import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getMorsel, getTask, getTree, getCard, getMessage } from '../api/mailbox';
import Linkify from './Linkify';
import Markdown from './Markdown';
import type { MorselSummary, TaskDetail, TreeNode, CardSummary, FeedMessage } from '../types/mailbox';
import { parseGitHubPrLink } from '../utils/links';

interface PeekDrawerProps {
  open: boolean;
  onClose: () => void;
  objectType: string;
  objectId: string;
}

const TYPE_LABELS: Record<string, string> = {
  morsel: 'Morsel',
  task: 'Task',
  tree: 'Tree',
  card: 'Card',
  message: 'Message',
  github_pr: 'GitHub PR',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-600 text-gray-200',
  launched: 'bg-blue-600 text-blue-100',
  in_progress: 'bg-amber-600 text-amber-100',
  completed: 'bg-emerald-600 text-emerald-100',
  failed: 'bg-red-600 text-red-100',
  killed: 'bg-orange-600 text-orange-100',
};

const PRIORITY_COLORS: Record<string, string> = {
  urgent: 'bg-red-600 text-white',
  high: 'bg-orange-600 text-white',
  normal: 'bg-gray-600 text-gray-200',
  low: 'bg-gray-700 text-gray-400',
};

const COLUMN_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  todo: 'To Do',
  in_progress: 'In Progress',
  done: 'Done',
  archived: 'Archived',
};

const senderColors: Record<string, string> = {
  ian: 'bg-purple-500/20 text-purple-300',
  doot: 'bg-indigo-500/20 text-indigo-300',
  oppy: 'bg-emerald-500/20 text-emerald-300',
  jerry: 'bg-amber-500/20 text-amber-300',
  kamaji: 'bg-cyan-500/20 text-cyan-300',
};

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// --- Peek renderers ---

function MorselPeek({ id }: { id: number }) {
  const [morsel, setMorsel] = useState<MorselSummary | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getMorsel(id).then(setMorsel).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <div className="text-red-400 text-sm">{error}</div>;
  if (!morsel) return <div className="text-gray-500 text-sm">Loading...</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${senderColors[morsel.creator] || 'bg-gray-700 text-gray-300'}`}>
          {morsel.creator}
        </span>
        <span className="text-xs text-gray-500">{formatDate(morsel.created_at)}</span>
      </div>
      {morsel.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {morsel.tags.map((tag) => (
            <span key={tag} className="px-1.5 py-0.5 rounded text-xs bg-gray-700 text-gray-300">{tag}</span>
          ))}
        </div>
      )}
      <Markdown className="text-sm text-gray-300">{morsel.body}</Markdown>
      {morsel.links.length > 0 && (
        <div className="border-t border-gray-800 pt-2">
          <div className="text-xs text-gray-500 mb-1">Linked objects</div>
          <div className="flex flex-wrap gap-1">
            {morsel.links.map((link, i) => (
              <span key={i} className="px-2 py-0.5 rounded text-xs bg-gray-700 text-gray-300">
                {link.object_type} #{link.object_id}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="pt-2">
        <Link to={`/morsels/${morsel.id}`} className="text-xs text-indigo-400 hover:text-indigo-300">
          Open full page &rarr;
        </Link>
      </div>
    </div>
  );
}

function TaskPeek({ id }: { id: number }) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getTask(id).then(setTask).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <div className="text-red-400 text-sm">{error}</div>;
  if (!task) return <div className="text-gray-500 text-sm">Loading...</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[task.status] || 'bg-gray-600 text-gray-200'}`}>
          {task.status}
        </span>
        <span className="text-xs text-gray-400">
          {task.creator} &rarr; {task.assignee}
        </span>
      </div>
      <div className="text-sm font-medium text-gray-200">{task.subject}</div>
      <div className="text-xs text-gray-500">Created {formatDate(task.created_at)}</div>
      {task.output && (
        <div>
          <div className="text-xs text-gray-500 mb-1">Output</div>
          <pre className="text-xs text-gray-400 whitespace-pre-wrap bg-gray-800 rounded p-2 max-h-48 overflow-y-auto"><Linkify>{task.output}</Linkify></pre>
        </div>
      )}
      {task.parent_task_id && (
        <div className="text-xs text-gray-400">
          Parent: task #{task.parent_task_id}
          {task.root_task_id && task.root_task_id !== task.id && <> | Tree #{task.root_task_id}</>}
        </div>
      )}
      {task.linked_cards && task.linked_cards.length > 0 && (
        <div>
          <div className="text-xs text-gray-500 mb-1">Cards</div>
          <div className="flex flex-wrap gap-1">
            {task.linked_cards.map(card => (
              <Link
                key={card.id}
                to={`/board/cards/${card.id}`}
                className="px-2 py-0.5 rounded text-xs font-medium bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 transition-colors"
              >
                #{card.id}: {card.title}
              </Link>
            ))}
          </div>
        </div>
      )}
      <div className="pt-2">
        <Link to={`/tasks/${task.id}`} className="text-xs text-indigo-400 hover:text-indigo-300">
          Open full page &rarr;
        </Link>
      </div>
    </div>
  );
}

function TreePeek({ id }: { id: number }) {
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getTree(id).then(setTree).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <div className="text-red-400 text-sm">{error}</div>;
  if (!tree) return <div className="text-gray-500 text-sm">Loading...</div>;

  function countNodes(node: TreeNode): { total: number; byStatus: Record<string, number> } {
    const byStatus: Record<string, number> = {};
    let total = 0;
    function walk(n: TreeNode) {
      total++;
      byStatus[n.status] = (byStatus[n.status] || 0) + 1;
      n.children.forEach(walk);
    }
    walk(node);
    return { total, byStatus };
  }

  const { total, byStatus } = countNodes(tree);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[tree.status] || 'bg-gray-600 text-gray-200'}`}>
          {tree.status}
        </span>
        <span className="text-xs text-gray-400">{total} tasks</span>
      </div>
      <div className="text-sm font-medium text-gray-200">{tree.subject}</div>
      <div className="text-xs text-gray-500">
        {tree.creator} &rarr; {tree.assignee} | Created {formatDate(tree.created_at)}
      </div>
      <div className="flex flex-wrap gap-1">
        {Object.entries(byStatus).map(([status, count]) => (
          <span key={status} className={`px-1.5 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[status] || 'bg-gray-600 text-gray-200'}`}>
            {count} {status}
          </span>
        ))}
      </div>
      {tree.output && (
        <div>
          <div className="text-xs text-gray-500 mb-1">Root output</div>
          <pre className="text-xs text-gray-400 whitespace-pre-wrap bg-gray-800 rounded p-2 max-h-32 overflow-y-auto"><Linkify>{tree.output}</Linkify></pre>
        </div>
      )}
      <div className="pt-2">
        <Link to={`/trees/${tree.id}`} className="text-xs text-indigo-400 hover:text-indigo-300">
          Open full page &rarr;
        </Link>
      </div>
    </div>
  );
}

function CardPeek({ id }: { id: number }) {
  const [card, setCard] = useState<CardSummary | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getCard(id).then(setCard).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <div className="text-red-400 text-sm">{error}</div>;
  if (!card) return <div className="text-gray-500 text-sm">Loading...</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-gray-400">{COLUMN_LABELS[card.col] || card.col}</span>
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${PRIORITY_COLORS[card.priority]}`}>
          {card.priority}
        </span>
      </div>
      <div className="text-sm font-medium text-gray-200">{card.title}</div>
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span>by {card.creator}</span>
        {card.assignee && <span>| @{card.assignee}</span>}
      </div>
      {card.labels.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {card.labels.map((l) => (
            <span key={l} className="px-1.5 py-0.5 rounded text-xs bg-gray-700 text-gray-300">{l}</span>
          ))}
        </div>
      )}
      {card.description && (
        <p className="text-sm text-gray-400 whitespace-pre-wrap"><Linkify>{card.description}</Linkify></p>
      )}
      <div className="pt-2">
        <Link to={`/board/cards/${card.id}`} className="text-xs text-indigo-400 hover:text-indigo-300">
          Open full page &rarr;
        </Link>
      </div>
    </div>
  );
}

function MessagePeek({ id }: { id: number }) {
  const [msg, setMsg] = useState<FeedMessage | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getMessage(id).then(setMsg).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <div className="text-red-400 text-sm">{error}</div>;
  if (!msg) return <div className="text-gray-500 text-sm">Loading...</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${senderColors[msg.sender] || 'bg-gray-700 text-gray-300'}`}>
          {msg.sender}
        </span>
        <span className="text-xs text-gray-400">&rarr; {msg.recipients.join(', ')}</span>
        <span className="text-xs text-gray-500 ml-auto">{formatDate(msg.created_at)}</span>
      </div>
      {msg.subject && <div className="text-sm font-medium text-gray-200">{msg.subject}</div>}
      <p className="text-sm text-gray-300 whitespace-pre-wrap"><Linkify>{msg.body}</Linkify></p>
      <div className="pt-2">
        <Link to={`/messages/${msg.id}`} className="text-xs text-indigo-400 hover:text-indigo-300">
          Open full page &rarr;
        </Link>
      </div>
    </div>
  );
}

// --- Main drawer ---

export default function PeekDrawer({ open, onClose, objectType, objectId }: PeekDrawerProps) {
  const id = parseInt(objectId, 10);
  const label = TYPE_LABELS[objectType] || objectType;

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  const renderContent = () => {
    switch (objectType) {
      case 'morsel': return <MorselPeek id={id} />;
      case 'task': return <TaskPeek id={id} />;
      case 'tree': return <TreePeek id={id} />;
      case 'card': return <CardPeek id={id} />;
      case 'message': return <MessagePeek id={id} />;
      case 'github_pr': {
        const parsed = parseGitHubPrLink(objectId);
        if (!parsed) return <div className="text-gray-400 text-sm">Invalid GitHub PR link: {objectId}</div>;
        return (
          <div className="space-y-3">
            <a
              href={parsed.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium bg-gray-800 text-gray-100 hover:bg-gray-700 border border-gray-600 transition-colors"
            >
              Open {parsed.label} on GitHub ↗
            </a>
          </div>
        );
      }
      default: return <div className="text-gray-400 text-sm">Unknown object type: {objectType}</div>;
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-[60] transition-opacity"
        onClick={onClose}
      />
      {/* Drawer panel */}
      <div className="fixed top-0 right-0 h-full w-full max-w-md bg-gray-900 border-l border-gray-700 z-[70] shadow-2xl overflow-y-auto animate-slide-in-right">
        {/* Header */}
        <div className="sticky top-0 bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-300">
            {objectType === 'github_pr' ? `${label}: ${objectId}` : `${label} #${objectId}`}
          </span>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-lg leading-none px-1"
            aria-label="Close"
          >
            &times;
          </button>
        </div>
        {/* Body */}
        <div className="p-4">
          {renderContent()}
        </div>
      </div>
    </>
  );
}
