import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { getMorsels } from '../api/mailbox';
import type { MorselSummary, MorselLink } from '../types/mailbox';
import { parseGitHubPrLink } from '../utils/links';

const senderColors: Record<string, string> = {
  ian: 'bg-purple-500/20 text-purple-300',
  doot: 'bg-indigo-500/20 text-indigo-300',
  oppy: 'bg-emerald-500/20 text-emerald-300',
  jerry: 'bg-amber-500/20 text-amber-300',
  kamaji: 'bg-cyan-500/20 text-cyan-300',
};

function formatRelativeDate(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function renderLink(link: MorselLink, index: number) {
  if (link.object_type === 'task') {
    return (
      <Link key={index} to={`/tasks/${link.object_id}`} className="text-xs text-indigo-400 hover:text-indigo-300" onClick={(e) => e.stopPropagation()}>
        task #{link.object_id}
      </Link>
    );
  }
  if (link.object_type === 'github_pr') {
    const parsed = parseGitHubPrLink(link.object_id);
    if (!parsed) return null;
    return (
      <a key={index} href={parsed.url} target="_blank" rel="noopener noreferrer" className="text-xs text-gray-100 bg-gray-800 hover:bg-gray-700 border border-gray-600 px-1.5 py-0.5 rounded font-medium transition-colors" onClick={(e) => e.stopPropagation()}>
        {parsed.label} ↗
      </a>
    );
  }
  return (
    <span key={index} className="text-xs text-gray-400">
      {link.object_type} {link.object_id}
    </span>
  );
}

function MorselCard({ morsel }: { morsel: MorselSummary }) {
  const navigate = useNavigate();
  return (
    <div
      className="rounded-lg border border-gray-800 p-3 cursor-pointer hover:bg-gray-800/50 transition-colors"
      onClick={() => navigate(`/morsels/${morsel.id}`)}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-xs font-mono text-gray-500">#{morsel.id}</span>
        <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${senderColors[morsel.creator] || 'bg-gray-700 text-gray-300'}`}>
          {morsel.creator}
        </span>
        {morsel.tags.map((tag) => (
          <span key={tag} className="inline-block rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-300">
            {tag}
          </span>
        ))}
        <span className="text-xs text-gray-600 ml-auto">{formatRelativeDate(morsel.created_at)}</span>
      </div>
      <p className="text-sm text-gray-300 whitespace-pre-wrap">{morsel.body}</p>
      {morsel.links.length > 0 && (
        <div className="flex items-center gap-2 mt-2">
          {morsel.links.map((link, i) => renderLink(link, i))}
        </div>
      )}
    </div>
  );
}

interface MorselPanelProps {
  objectType: string;
  objectId: string | number;
}

export default function MorselPanel({ objectType, objectId }: MorselPanelProps) {
  const [morsels, setMorsels] = useState<MorselSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getMorsels({ object_type: objectType, object_id: String(objectId), limit: 20 })
      .then(setMorsels)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [objectType, objectId]);

  if (loading) return null;
  if (morsels.length === 0) return null;

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 mb-4">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Morsels</h3>
      <div className="space-y-2">
        {morsels.map((m) => (
          <MorselCard key={m.id} morsel={m} />
        ))}
      </div>
    </div>
  );
}

export { MorselCard };
