import { useEffect, useState, useCallback } from 'react';
import { getFeed } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import MessageCard from '../components/MessageCard';
import SearchBar from '../components/SearchBar';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import type { FeedMessage } from '../types/mailbox';

const BROTHERS = ['', 'ian', 'doot', 'oppy', 'jerry'];

export default function FeedPage() {
  useDocumentTitle('Feed');
  const [messages, setMessages] = useState<FeedMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [sender, setSender] = useState('');
  const [recipient, setRecipient] = useState('');
  const apiKey = useAuthStore((s) => s.apiKey);

  const fetchFeed = useCallback(
    async (offset = 0, append = false) => {
      if (!apiKey) return;
      const setter = offset === 0 ? setLoading : setLoadingMore;
      setter(true);
      try {
        const params: Record<string, string | number> = { limit: 50, offset };
        if (sender) params.sender = sender;
        if (recipient) params.recipient = recipient;
        if (query.trim()) params.q = query.trim();
        const data = await getFeed(params);
        setHasMore(data.length === 50);
        setMessages((prev) => (append ? [...prev, ...data] : data));
      } catch (e: any) {
        setError(e.message);
      } finally {
        setter(false);
      }
    },
    [apiKey, sender, recipient, query]
  );

  useEffect(() => {
    fetchFeed();
  }, [fetchFeed]);

  if (!apiKey) {
    return <p className="text-gray-400">Set your API key in <a href="/settings" className="text-indigo-400 underline">Settings</a> first.</p>;
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Feed</h1>
      <SearchBar query={query} onQueryChange={setQuery} placeholder="Search feed...">
        <select
          value={sender}
          onChange={(e) => setSender(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
        >
          <option value="">All senders</option>
          {BROTHERS.filter(Boolean).map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
        <select
          value={recipient}
          onChange={(e) => setRecipient(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
        >
          <option value="">All recipients</option>
          {BROTHERS.filter(Boolean).map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
      </SearchBar>
      {loading && <p className="text-gray-500">Loading...</p>}
      {error && <p className="text-red-400">{error}</p>}
      {!loading && messages.length === 0 && <p className="text-gray-500">No messages.</p>}
      <div className="space-y-2">
        {messages.map((msg) => (
          <MessageCard key={msg.id} message={msg} />
        ))}
      </div>
      {hasMore && messages.length > 0 && (
        <button
          onClick={() => fetchFeed(messages.length, true)}
          disabled={loadingMore}
          className="mt-4 w-full rounded-lg border border-gray-700 py-2 text-sm text-gray-400 hover:bg-gray-800 transition-colors disabled:opacity-50"
        >
          {loadingMore ? 'Loading...' : 'Load more'}
        </button>
      )}
    </div>
  );
}
