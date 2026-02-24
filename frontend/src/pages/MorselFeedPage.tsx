import { useEffect, useState, useCallback } from 'react';
import { getMorsels, getMemberActivity } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import { MorselCard } from '../components/MorselPanel';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import type { MorselSummary } from '../types/mailbox';

export default function MorselFeedPage() {
  useDocumentTitle('Morsels');
  const [morsels, setMorsels] = useState<MorselSummary[]>([]);
  const [members, setMembers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [creator, setCreator] = useState('');
  const [tag, setTag] = useState('');
  const [hasMore, setHasMore] = useState(true);
  const apiKey = useAuthStore((s) => s.apiKey);

  useEffect(() => {
    if (!apiKey) return;
    getMemberActivity()
      .then((res) => setMembers(res.members.map((m) => m.name)))
      .catch(() => {});
  }, [apiKey]);

  const fetchMorsels = useCallback(async (append = false) => {
    if (!apiKey) return;
    if (!append) setLoading(true);
    else setLoadingMore(true);
    try {
      const offset = append ? morsels.length : 0;
      const params: Record<string, string | number> = { limit: 50, offset };
      if (creator) params.creator = creator;
      if (tag) params.tag = tag;
      const data = await getMorsels(params);
      if (append) {
        setMorsels((prev) => [...prev, ...data]);
      } else {
        setMorsels(data);
      }
      setHasMore(data.length === 50);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [apiKey, creator, tag, morsels.length]);

  useEffect(() => {
    fetchMorsels(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey, creator, tag]);

  if (!apiKey) {
    return <p className="text-gray-400">Set your API key in <a href="/settings" className="text-indigo-400 underline">Settings</a> first.</p>;
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Morsels</h1>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select
          value={creator}
          onChange={(e) => setCreator(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
        >
          <option value="">All creators</option>
          {members.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <input
          type="text"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          placeholder="Filter by tag..."
          className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500"
        />
      </div>
      {loading && <p className="text-gray-500">Loading...</p>}
      {error && <p className="text-red-400">{error}</p>}
      {!loading && morsels.length === 0 && <p className="text-gray-500">No morsels.</p>}
      <div className="space-y-2">
        {morsels.map((m) => (
          <MorselCard key={m.id} morsel={m} />
        ))}
      </div>
      {hasMore && morsels.length > 0 && (
        <button
          onClick={() => fetchMorsels(true)}
          disabled={loadingMore}
          className="mt-4 w-full rounded-lg border border-gray-700 py-2 text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors disabled:opacity-50"
        >
          {loadingMore ? 'Loading...' : 'Load more'}
        </button>
      )}
    </div>
  );
}
