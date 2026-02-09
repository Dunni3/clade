import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { viewMessage, editMessage, deleteMessage, markUnread } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import DeleteModal from '../components/DeleteModal';
import type { FeedMessage, EditMessageRequest } from '../types/mailbox';

const senderColors: Record<string, string> = {
  ian: 'bg-purple-500/20 text-purple-300',
  doot: 'bg-indigo-500/20 text-indigo-300',
  oppy: 'bg-emerald-500/20 text-emerald-300',
  jerry: 'bg-amber-500/20 text-amber-300',
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

export default function MessageDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [message, setMessage] = useState<FeedMessage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [editSubject, setEditSubject] = useState('');
  const [editBody, setEditBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const brotherName = useAuthStore((s) => s.brotherName);

  const canEdit = message && (message.sender === brotherName || brotherName === 'doot' || brotherName === 'ian');

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    viewMessage(Number(id))
      .then((msg) => {
        setMessage(msg);
        setEditSubject(msg.subject);
        setEditBody(msg.body);
      })
      .catch((e) => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleSave() {
    if (!message) return;
    setSaving(true);
    try {
      const req: EditMessageRequest = {};
      if (editSubject !== message.subject) req.subject = editSubject;
      if (editBody !== message.body) req.body = editBody;
      const updated = await editMessage(message.id, req);
      setMessage(updated);
      setEditing(false);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!message) return;
    setDeleting(true);
    try {
      await deleteMessage(message.id);
      navigate('/feed');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
      setDeleting(false);
    }
  }

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!message) return <p className="text-gray-500">Message not found.</p>;

  return (
    <div>
      <button onClick={() => navigate(-1)} className="text-sm text-gray-400 hover:text-gray-200 mb-4 inline-block">
        &larr; Back
      </button>

      {editing ? (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-6">
          <label className="block text-sm text-gray-400 mb-1">Subject</label>
          <input
            value={editSubject}
            onChange={(e) => setEditSubject(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 mb-4 focus:border-indigo-500 focus:outline-none"
          />
          <label className="block text-sm text-gray-400 mb-1">Body</label>
          <textarea
            value={editBody}
            onChange={(e) => setEditBody(e.target.value)}
            rows={8}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 mb-4 focus:border-indigo-500 focus:outline-none resize-y"
          />
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setEditSubject(message.subject);
                setEditBody(message.body);
              }}
              className="px-4 py-2 text-sm rounded-lg border border-gray-600 text-gray-300 hover:bg-gray-800 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${senderColors[message.sender] || 'bg-gray-700 text-gray-300'}`}>
                  {message.sender}
                </span>
                <span className="text-xs text-gray-500">to {message.recipients.join(', ')}</span>
              </div>
              <h1 className="text-xl font-semibold text-gray-100">
                {message.subject || '(no subject)'}
              </h1>
            </div>
            <span className="text-xs text-gray-500 whitespace-nowrap">{formatDate(message.created_at)}</span>
          </div>

          <div className="text-sm text-gray-300 whitespace-pre-wrap mb-6">{message.body}</div>

          {message.read_by.length > 0 && (
            <div className="border-t border-gray-800 pt-4 mb-4">
              <p className="text-xs text-gray-500 mb-2">Read by</p>
              <div className="flex flex-wrap gap-2">
                {message.read_by.map((r) => (
                  <span key={r.brother} className="text-xs rounded bg-gray-800 px-2 py-1 text-gray-400">
                    {r.brother} <span className="text-gray-600">{formatDate(r.read_at)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-3 border-t border-gray-800 pt-4">
            <button
              onClick={async () => {
                await markUnread(message.id);
                navigate(-1);
              }}
              className="px-4 py-2 text-sm rounded-lg border border-gray-600 text-gray-300 hover:bg-gray-800 transition-colors"
            >
              Mark as unread
            </button>
            {canEdit && (
              <>
                <button
                  onClick={() => setEditing(true)}
                  className="px-4 py-2 text-sm rounded-lg border border-gray-600 text-gray-300 hover:bg-gray-800 transition-colors"
                >
                  Edit
                </button>
                <button
                  onClick={() => setShowDelete(true)}
                  className="px-4 py-2 text-sm rounded-lg border border-red-800 text-red-400 hover:bg-red-900/30 transition-colors"
                >
                  Delete
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <DeleteModal
        open={showDelete}
        onConfirm={handleDelete}
        onCancel={() => setShowDelete(false)}
        loading={deleting}
      />
    </div>
  );
}
