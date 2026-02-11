import { Link } from 'react-router-dom';
import type { MessageSummary, FeedMessage } from '../types/mailbox';

type CardMessage = MessageSummary | FeedMessage;

function isInboxMessage(msg: CardMessage): msg is MessageSummary {
  return 'is_read' in msg;
}

function formatDate(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 86400000) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  if (diff < 604800000) {
    return d.toLocaleDateString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

const senderColors: Record<string, string> = {
  ian: 'bg-purple-500/20 text-purple-300',
  doot: 'bg-indigo-500/20 text-indigo-300',
  oppy: 'bg-emerald-500/20 text-emerald-300',
  jerry: 'bg-amber-500/20 text-amber-300',
};

export default function MessageCard({ message }: { message: CardMessage }) {
  const unread = isInboxMessage(message) && !message.is_read;

  return (
    <Link
      to={`/messages/${message.id}`}
      className={`block rounded-lg border p-4 transition-colors hover:bg-gray-800/50 ${
        unread ? 'border-indigo-500/50 bg-gray-800/30' : 'border-gray-800'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-gray-500">#{message.id}</span>
            <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${senderColors[message.sender] || 'bg-gray-700 text-gray-300'}`}>
              {message.sender}
            </span>
            {'recipients' in message && (
              <span className="text-xs text-gray-500">
                to {(message as FeedMessage).recipients.join(', ')}
              </span>
            )}
            {unread && (
              <span className="h-2 w-2 rounded-full bg-indigo-400" />
            )}
          </div>
          <p className={`text-sm truncate ${unread ? 'font-semibold text-gray-100' : 'text-gray-300'}`}>
            {message.subject || '(no subject)'}
          </p>
          <p className="text-xs text-gray-500 truncate mt-0.5">{message.body}</p>
        </div>
        <span className="text-xs text-gray-500 whitespace-nowrap">{formatDate(message.created_at)}</span>
      </div>
    </Link>
  );
}
