import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { getMorsel } from '../api/mailbox';
import type { MorselSummary } from '../types/mailbox';

const senderColors: Record<string, string> = {
  ian: 'bg-purple-500/20 text-purple-300',
  doot: 'bg-indigo-500/20 text-indigo-300',
  oppy: 'bg-emerald-500/20 text-emerald-300',
  jerry: 'bg-amber-500/20 text-amber-300',
  kamaji: 'bg-cyan-500/20 text-cyan-300',
};

const linkColorMap: Record<string, string> = {
  task: 'bg-indigo-900/50 text-indigo-300 hover:bg-indigo-900',
  morsel: 'bg-amber-900/50 text-amber-300 hover:bg-amber-900',
  tree: 'bg-cyan-900/50 text-cyan-300 hover:bg-cyan-900',
  message: 'bg-purple-900/50 text-purple-300 hover:bg-purple-900',
  card: 'bg-emerald-900/50 text-emerald-300 hover:bg-emerald-900',
};

const linkHrefMap: Record<string, (id: string) => string> = {
  task: (id) => `/tasks/${id}`,
  tree: (id) => `/trees/${id}`,
  card: (id) => `/board?card=${id}`,
  morsel: (id) => `/morsels/${id}`,
  message: (id) => `/messages/${id}`,
};

export default function MorselDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [morsel, setMorsel] = useState<MorselSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getMorsel(parseInt(id, 10))
      .then(setMorsel)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="text-gray-400">Loading...</div>;
  if (error) return <div className="text-red-400">{error}</div>;
  if (!morsel) return <div className="text-gray-400">Morsel not found.</div>;

  const date = new Date(morsel.created_at);
  const dateStr = date.toLocaleString([], {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });

  return (
    <div className="max-w-2xl">
      <button
        onClick={() => navigate(-1)}
        className="text-sm text-gray-400 hover:text-gray-200 mb-4 inline-block"
      >
        &larr; Back
      </button>

      <div className="rounded-xl border border-gray-700 bg-gray-900 p-5">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-gray-500">Morsel #{morsel.id}</span>
            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${senderColors[morsel.creator] || 'bg-gray-700 text-gray-300'}`}>
              {morsel.creator}
            </span>
          </div>
          <span className="text-xs text-gray-500">{dateStr}</span>
        </div>

        {/* Tags */}
        {morsel.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-4">
            {morsel.tags.map((tag) => (
              <span key={tag} className="px-2 py-0.5 rounded text-xs bg-gray-700 text-gray-300">{tag}</span>
            ))}
          </div>
        )}

        {/* Body */}
        <div className="text-sm text-gray-300 whitespace-pre-wrap mb-4">{morsel.body}</div>

        {/* Linked objects */}
        {morsel.links.length > 0 && (
          <div className="border-t border-gray-800 pt-3">
            <div className="text-xs text-gray-500 mb-2">Linked objects</div>
            <div className="flex flex-wrap gap-1.5">
              {morsel.links.map((link, i) => {
                const colors = linkColorMap[link.object_type] || 'bg-gray-700 text-gray-300';
                const hrefFn = linkHrefMap[link.object_type];
                const label = `${link.object_type} #${link.object_id}`;
                if (hrefFn) {
                  return (
                    <Link key={i} to={hrefFn(link.object_id)} className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${colors}`}>
                      {label}
                    </Link>
                  );
                }
                return (
                  <span key={i} className={`px-2 py-0.5 rounded text-xs font-medium ${colors}`}>
                    {label}
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
