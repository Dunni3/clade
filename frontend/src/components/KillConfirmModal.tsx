interface KillConfirmModalProps {
  open: boolean;
  subject: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export default function KillConfirmModal({ open, subject, onConfirm, onCancel, loading }: KillConfirmModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="rounded-xl bg-gray-900 border border-gray-700 p-6 max-w-sm w-full mx-4">
        <h3 className="text-lg font-semibold text-gray-100 mb-2">Kill task?</h3>
        <p className="text-sm text-gray-400 mb-1">
          This will terminate the tmux session for:
        </p>
        <p className="text-sm text-orange-300 font-medium mb-4 truncate">
          {subject || '(no subject)'}
        </p>
        <p className="text-xs text-gray-500 mb-6">
          Killed tasks cannot be resumed or retried.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg border border-gray-600 text-gray-300 hover:bg-gray-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg bg-orange-600 text-white hover:bg-orange-700 transition-colors disabled:opacity-50"
          >
            {loading ? 'Killing...' : 'Kill Task'}
          </button>
        </div>
      </div>
    </div>
  );
}
