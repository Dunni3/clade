import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import { getTree, killTask } from '../api/mailbox';
import KillConfirmModal from '../components/KillConfirmModal';
import MorselPanel from '../components/MorselPanel';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import type { TreeNode } from '../types/mailbox';

const statusColors: Record<string, string> = {
  pending: 'border-gray-500 bg-gray-500/10',
  launched: 'border-blue-500 bg-blue-500/10',
  in_progress: 'border-amber-500 bg-amber-500/10',
  completed: 'border-emerald-500 bg-emerald-500/10',
  failed: 'border-red-500 bg-red-500/10',
  killed: 'border-orange-500 bg-orange-500/10',
};

const statusBadgeColors: Record<string, string> = {
  pending: 'bg-gray-500/20 text-gray-300',
  launched: 'bg-blue-500/20 text-blue-300',
  in_progress: 'bg-amber-500/20 text-amber-300',
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
  killed: 'bg-orange-500/20 text-orange-300',
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

const NODE_WIDTH = 280;
const NODE_HEIGHT = 80;

type TaskNodeData = {
  taskId: number;
  subject: string;
  assignee: string;
  status: string;
  blockedByTaskId: number | null;
};

function TaskNode({ data }: NodeProps<Node<TaskNodeData>>) {
  const isBlocked = data.blockedByTaskId && data.status === 'pending';
  const borderClass = isBlocked
    ? 'border-yellow-500 bg-yellow-500/10'
    : (statusColors[data.status] || 'border-gray-600 bg-gray-800/50');
  return (
    <div
      className={`rounded-lg border-2 px-3 py-2 ${borderClass}`}
      style={{ width: NODE_WIDTH, minHeight: NODE_HEIGHT }}
    >
      <Handle type="target" position={Position.Top} className="!bg-gray-500 !w-2 !h-2" />
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-xs font-mono text-gray-500">#{data.taskId}</span>
        <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${isBlocked ? 'bg-yellow-500/20 text-yellow-300' : (statusBadgeColors[data.status] || 'bg-gray-700 text-gray-300')}`}>
          {isBlocked ? `blocked by #${data.blockedByTaskId}` : data.status}
        </span>
      </div>
      <p className="text-sm text-gray-200 truncate">{data.subject || '(no subject)'}</p>
      <p className="text-xs text-gray-500 mt-0.5">{data.assignee}</p>
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500 !w-2 !h-2" />
    </div>
  );
}

const nodeTypes = { taskNode: TaskNode };

function layoutTree(root: TreeNode): { nodes: Node<TaskNodeData>[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60 });
  g.setDefaultEdgeLabel(() => ({}));

  const nodeDataMap = new Map<string, TaskNodeData>();
  // Track secondary parent edges for multi-parent DAG support
  const secondaryEdges: { source: string; target: string }[] = [];

  function walk(node: TreeNode) {
    const id = String(node.id);
    g.setNode(id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    nodeDataMap.set(id, {
      taskId: node.id,
      subject: node.subject,
      assignee: node.assignee,
      status: node.status,
      blockedByTaskId: node.blocked_by_task_id,
    });
    // Add primary parent → child edges (tree structure)
    for (const child of node.children) {
      g.setEdge(id, String(child.id));
      walk(child);
    }
    // Track secondary parent edges from parent_task_ids
    const parentIds = node.parent_task_ids || [];
    if (parentIds.length > 1) {
      // Skip primary parent (index 0) — already handled by tree structure
      for (let i = 1; i < parentIds.length; i++) {
        secondaryEdges.push({ source: String(parentIds[i]), target: id });
      }
    }
  }
  walk(root);

  // Add secondary parent edges to the graph for dagre layout
  for (const se of secondaryEdges) {
    if (g.hasNode(se.source) && g.hasNode(se.target)) {
      g.setEdge(se.source, se.target);
    }
  }

  dagre.layout(g);

  const nodes: Node<TaskNodeData>[] = g.nodes().map((id) => {
    const pos = g.node(id);
    return {
      id,
      type: 'taskNode',
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: nodeDataMap.get(id)!,
    };
  });

  // Build a set of secondary edge keys for styling
  const secondaryEdgeKeys = new Set(secondaryEdges.map(se => `${se.source}-${se.target}`));

  const edges: Edge[] = g.edges().map((e) => {
    const key = `${e.v}-${e.w}`;
    const isSecondary = secondaryEdgeKeys.has(key);
    return {
      id: key,
      source: e.v,
      target: e.w,
      type: 'smoothstep',
      animated: nodeDataMap.get(e.w)?.status === 'in_progress',
      style: {
        stroke: isSecondary ? '#6366f1' : '#4b5563',
        strokeDasharray: isSecondary ? '5 5' : undefined,
      },
    };
  });

  return { nodes, edges };
}

function findNode(root: TreeNode, id: number): TreeNode | null {
  if (root.id === id) return root;
  for (const child of root.children) {
    const found = findNode(child, id);
    if (found) return found;
  }
  return null;
}

export default function TreeDetailPage() {
  const { rootId } = useParams<{ rootId: string }>();
  const navigate = useNavigate();
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [showKillModal, setShowKillModal] = useState(false);
  const [killLoading, setKillLoading] = useState(false);

  useDocumentTitle(tree ? `Tree #${tree.id} \u2013 ${tree.subject || '(no subject)'}` : undefined);

  const fetchTree = useCallback(async () => {
    if (!rootId) return;
    try {
      const data = await getTree(Number(rootId));
      setTree(data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
    }
  }, [rootId]);

  useEffect(() => {
    setLoading(true);
    fetchTree().finally(() => setLoading(false));
  }, [fetchTree]);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!tree) return <p className="text-gray-500">Tree not found.</p>;

  const { nodes, edges } = layoutTree(tree);
  const selectedTask = selectedNodeId ? findNode(tree, selectedNodeId) : null;
  const selectedIsActive = selectedTask && ['pending', 'launched', 'in_progress'].includes(selectedTask.status);

  const handleKill = async () => {
    if (!selectedTask) return;
    setKillLoading(true);
    try {
      await killTask(selectedTask.id);
      await fetchTree();
    } catch {
      await fetchTree();
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

      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-2xl font-bold">Tree #{tree.id}</h1>
        <span className="text-sm text-gray-400">{tree.subject}</span>
      </div>

      {/* Graph */}
      <div style={{ height: 500 }} className="rounded-xl border border-gray-700 bg-gray-900 mb-4">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          nodesDraggable={false}
          onNodeClick={(_event, node) => setSelectedNodeId(node.data.taskId)}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#374151" gap={16} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      {/* Selected node detail panel */}
      {selectedTask && (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-gray-500">#{selectedTask.id}</span>
              <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${statusBadgeColors[selectedTask.status] || 'bg-gray-700 text-gray-300'}`}>
                {selectedTask.status}
              </span>
              <span className="text-xs text-gray-500">
                {selectedTask.creator} &rarr; {selectedTask.assignee}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {selectedIsActive && (
                <button
                  onClick={() => setShowKillModal(true)}
                  className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-orange-500/20 text-orange-300 hover:bg-orange-500/30 transition-colors"
                >
                  Kill
                </button>
              )}
              <Link to={`/tasks/${selectedTask.id}`} className="text-xs text-indigo-400 hover:text-indigo-300">
                Full detail &rarr;
              </Link>
            </div>
          </div>
          <h2 className="text-sm font-semibold text-gray-200 mb-2">{selectedTask.subject || '(no subject)'}</h2>
          {selectedTask.blocked_by_task_id && (
            <div className="mb-2">
              <Link
                to={`/tasks/${selectedTask.blocked_by_task_id}`}
                className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-yellow-500/20 text-yellow-300 hover:bg-yellow-500/30 transition-colors"
              >
                Blocked by #{selectedTask.blocked_by_task_id}
              </Link>
            </div>
          )}
          <div className="flex flex-wrap gap-4 text-xs text-gray-500 mb-3">
            <span>Created: {formatDate(selectedTask.created_at)}</span>
            {selectedTask.started_at && <span>Started: {formatDate(selectedTask.started_at)}</span>}
            {selectedTask.completed_at && <span>Completed: {formatDate(selectedTask.completed_at)}</span>}
          </div>
          {selectedTask.prompt && (
            <details className="mb-2">
              <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-200">Prompt</summary>
              <pre className="mt-2 text-xs text-gray-500 whitespace-pre-wrap overflow-x-auto max-h-40 overflow-y-auto">{selectedTask.prompt}</pre>
            </details>
          )}
          {selectedTask.output && (
            <div>
              <p className="text-xs text-gray-400 mb-1">Output</p>
              <pre className="text-xs text-gray-500 whitespace-pre-wrap overflow-x-auto max-h-40 overflow-y-auto">{selectedTask.output}</pre>
            </div>
          )}
          {selectedTask.linked_cards && selectedTask.linked_cards.length > 0 && (
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              {selectedTask.linked_cards.map(card => (
                <Link
                  key={card.id}
                  to={`/board/cards/${card.id}`}
                  className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 transition-colors"
                >
                  Card #{card.id}: {card.title}
                </Link>
              ))}
            </div>
          )}
          <MorselPanel objectType="task" objectId={selectedTask.id} />
        </div>
      )}

      {/* Root task morsels (when no task selected) */}
      {!selectedTask && <MorselPanel objectType="task" objectId={tree.id} />}

      {selectedTask && (
        <KillConfirmModal
          open={showKillModal}
          subject={selectedTask.subject}
          onConfirm={handleKill}
          onCancel={() => setShowKillModal(false)}
          loading={killLoading}
        />
      )}
    </div>
  );
}
