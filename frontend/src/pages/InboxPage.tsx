import { useEffect, useState, useMemo } from 'react';
import { getInbox } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import MessageCard from '../components/MessageCard';
import SearchBar from '../components/SearchBar';
import type { MessageSummary } from '../types/mailbox';

export default function InboxPage() {
  const [messages, setMessages] = useState<MessageSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  const apiKey = useAuthStore((s) => s.apiKey);

  useEffect(() => {
    if (!apiKey) return;
    setLoading(true);
    getInbox(false, 200)
      .then(setMessages)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [apiKey]);

  const filtered = useMemo(() => {
    let msgs = messages;
    if (filter === 'unread') {
      msgs = msgs.filter((m) => !m.is_read);
    }
    if (query.trim()) {
      const q = query.toLowerCase();
      msgs = msgs.filter(
        (m) =>
          m.subject.toLowerCase().includes(q) ||
          m.body.toLowerCase().includes(q) ||
          m.sender.toLowerCase().includes(q)
      );
    }
    return msgs;
  }, [messages, filter, query]);

  if (!apiKey) {
    return <p className="text-gray-400">Set your API key in <a href="/settings" className="text-indigo-400 underline">Settings</a> first.</p>;
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Inbox</h1>
      <SearchBar query={query} onQueryChange={setQuery} placeholder="Search inbox...">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as 'all' | 'unread')}
          className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
        >
          <option value="all">All</option>
          <option value="unread">Unread</option>
        </select>
      </SearchBar>
      {loading && <p className="text-gray-500">Loading...</p>}
      {error && <p className="text-red-400">{error}</p>}
      {!loading && filtered.length === 0 && <p className="text-gray-500">No messages.</p>}
      <div className="space-y-2">
        {filtered.map((msg) => (
          <MessageCard key={msg.id} message={msg} />
        ))}
      </div>
    </div>
  );
}
