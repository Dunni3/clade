import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { sendMessage } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import { useDocumentTitle } from '../hooks/useDocumentTitle';

const ALL_BROTHERS = ['doot', 'oppy', 'jerry'];

export default function ComposePage() {
  useDocumentTitle('Compose');
  const navigate = useNavigate();
  const brotherName = useAuthStore((s) => s.brotherName);
  const [recipients, setRecipients] = useState<string[]>([]);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const availableRecipients = brotherName === 'ian'
    ? ALL_BROTHERS
    : ALL_BROTHERS.filter((b) => b !== brotherName);

  function toggleRecipient(name: string) {
    setRecipients((prev) =>
      prev.includes(name) ? prev.filter((r) => r !== name) : [...prev, name]
    );
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (recipients.length === 0) {
      setError('Select at least one recipient');
      return;
    }
    if (!body.trim()) {
      setError('Body is required');
      return;
    }
    setSending(true);
    setError('');
    try {
      const result = await sendMessage({ recipients, subject, body });
      navigate(`/messages/${result.id}`);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
      setSending(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Compose</h1>
      <form onSubmit={handleSend} className="rounded-xl border border-gray-700 bg-gray-900 p-6 space-y-4">
        <div>
          <label className="block text-sm text-gray-400 mb-2">Recipients</label>
          <div className="flex gap-2">
            {availableRecipients.map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => toggleRecipient(name)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  recipients.includes(name)
                    ? 'bg-indigo-600 text-white'
                    : 'border border-gray-600 text-gray-400 hover:bg-gray-800'
                }`}
              >
                {name}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Subject</label>
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="(optional)"
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Body</label>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={8}
            placeholder="Write your message..."
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-indigo-500 focus:outline-none resize-y"
          />
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={sending}
          className="px-6 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
        >
          {sending ? 'Sending...' : 'Send'}
        </button>
      </form>
    </div>
  );
}
