import { useEffect, useState } from 'react';
import { getEmbers, getEmberStatus, updateEmberPermissions } from '../api/mailbox';
import { useAuthStore } from '../store/authStore';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import type { EmberEntry, EmberInfo } from '../types/mailbox';

const PRESETS: { label: string; value: string; description: string }[] = [
  { label: 'CC defaults', value: '', description: 'Standard Claude Code permission prompts' },
  { label: 'Full autonomy', value: '--dangerously-skip-permissions', description: 'Skip all permission prompts' },
  { label: 'Read-only', value: '--permission-mode default --allowedTools Read,Grep,Glob', description: 'Read-only tools only' },
  { label: 'No Python', value: '--disallowedTools "Bash(python*)" "Bash(pip*)" "Bash(conda*)"', description: 'Block Python execution' },
];

function detectPreset(flags: string): string {
  const match = PRESETS.find((p) => p.value === flags);
  return match ? match.label : 'Custom';
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return 'never';
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

const memberColors: Record<string, string> = {
  doot: 'border-indigo-500',
  oppy: 'border-emerald-500',
  jerry: 'border-amber-500',
};

interface EditState {
  preset: string;
  customFlags: string;
}

export default function CladeSettingsPage() {
  useDocumentTitle('Clade Settings');
  const [embers, setEmbers] = useState<EmberEntry[]>([]);
  const [emberStatus, setEmberStatus] = useState<Record<string, EmberInfo>>({});
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Record<string, EditState>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const apiKey = useAuthStore((s) => s.apiKey);

  useEffect(() => {
    if (!apiKey) return;
    setLoading(true);
    Promise.allSettled([
      getEmbers().then(setEmbers).catch(() => {}),
      getEmberStatus().then((res) => setEmberStatus(res.embers)).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, [apiKey]);

  function startEdit(ember: EmberEntry) {
    const preset = detectPreset(ember.permission_flags);
    setEditing((prev) => ({
      ...prev,
      [ember.name]: {
        preset,
        customFlags: preset === 'Custom' ? ember.permission_flags : '',
      },
    }));
    setErrors((prev) => ({ ...prev, [ember.name]: '' }));
  }

  function cancelEdit(name: string) {
    setEditing((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    setErrors((prev) => ({ ...prev, [name]: '' }));
  }

  function getEffectiveFlags(name: string): string {
    const state = editing[name];
    if (!state) return '';
    if (state.preset === 'Custom') return state.customFlags;
    return PRESETS.find((p) => p.label === state.preset)?.value ?? '';
  }

  async function savePermissions(name: string) {
    const flags = getEffectiveFlags(name);
    setSaving((prev) => ({ ...prev, [name]: true }));
    setErrors((prev) => ({ ...prev, [name]: '' }));
    try {
      const updated = await updateEmberPermissions(name, { permission_flags: flags });
      setEmbers((prev) => prev.map((e) => (e.name === name ? updated : e)));
      cancelEdit(name);
    } catch {
      setErrors((prev) => ({ ...prev, [name]: 'Save failed. Please try again.' }));
    } finally {
      setSaving((prev) => ({ ...prev, [name]: false }));
    }
  }

  if (!apiKey) {
    return (
      <p className="text-gray-400">
        Set your API key in{' '}
        <a href="/settings" className="text-indigo-400 underline">
          Settings
        </a>{' '}
        first.
      </p>
    );
  }

  if (loading) return <p className="text-gray-500">Loading...</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Clade Settings</h1>

      <h2 className="text-lg font-semibold text-gray-200 mb-3">Brother Permissions</h2>
      <p className="text-sm text-gray-500 mb-4">
        Configure per-brother Claude Code permission flags. Changes take effect on the next task execution.
      </p>

      {embers.length === 0 ? (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-6 text-center">
          <p className="text-gray-500 text-sm">No Embers registered.</p>
          <p className="text-gray-600 text-xs mt-1">Register an Ember to configure per-brother permissions.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {embers.map((ember) => {
            const isEditing = !!editing[ember.name];
            const editState = editing[ember.name];
            const status = emberStatus[ember.name];
            const borderColor = memberColors[ember.name] || 'border-gray-600';
            const isOnline = status?.status === 'ok';
            const presetLabel = detectPreset(ember.permission_flags);

            return (
              <div
                key={ember.name}
                className={`rounded-xl border-l-4 ${borderColor} border border-gray-700 bg-gray-900 p-4`}
              >
                {/* Header row */}
                <div className="flex items-center gap-3 mb-3">
                  <div
                    className={`h-2 w-2 rounded-full flex-shrink-0 ${isOnline ? 'bg-emerald-400' : 'bg-gray-600'}`}
                    title={isOnline ? 'Ember online' : 'Ember offline'}
                  />
                  <span className="text-sm font-semibold text-gray-100">{ember.name}</span>
                  {!isEditing && (
                    <span
                      className={`ml-1 inline-block rounded px-2 py-0.5 text-xs font-medium ${
                        presetLabel === 'Full autonomy'
                          ? 'bg-amber-500/20 text-amber-300'
                          : presetLabel === 'CC defaults'
                          ? 'bg-gray-700 text-gray-400'
                          : presetLabel === 'Read-only'
                          ? 'bg-blue-500/20 text-blue-300'
                          : 'bg-gray-700 text-gray-300'
                      }`}
                    >
                      {presetLabel}
                    </span>
                  )}
                  <span className="text-xs text-gray-600 ml-auto">
                    updated {formatRelativeTime(ember.updated_at)}
                  </span>
                  {!isEditing && (
                    <button
                      onClick={() => startEdit(ember)}
                      className="px-3 py-1 text-xs rounded-lg border border-gray-600 text-gray-300 hover:bg-gray-800 transition-colors"
                    >
                      Edit
                    </button>
                  )}
                </div>

                {/* Current flags display (when not editing) */}
                {!isEditing && ember.permission_flags && (
                  <code className="block text-xs text-gray-500 font-mono bg-gray-800/50 rounded px-2 py-1 truncate">
                    {ember.permission_flags}
                  </code>
                )}
                {!isEditing && !ember.permission_flags && (
                  <p className="text-xs text-gray-600 italic">No flags — using CC defaults</p>
                )}

                {/* Edit form */}
                {isEditing && editState && (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Preset</label>
                      <select
                        value={editState.preset}
                        onChange={(e) =>
                          setEditing((prev) => ({
                            ...prev,
                            [ember.name]: { ...prev[ember.name], preset: e.target.value },
                          }))
                        }
                        className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-indigo-500 focus:outline-none"
                      >
                        {PRESETS.map((p) => (
                          <option key={p.label} value={p.label}>
                            {p.label} — {p.description}
                          </option>
                        ))}
                        <option value="Custom">Custom</option>
                      </select>
                    </div>

                    {editState.preset === 'Custom' && (
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">Permission flags</label>
                        <input
                          type="text"
                          value={editState.customFlags}
                          onChange={(e) =>
                            setEditing((prev) => ({
                              ...prev,
                              [ember.name]: { ...prev[ember.name], customFlags: e.target.value },
                            }))
                          }
                          placeholder="e.g. --dangerously-skip-permissions"
                          className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm font-mono text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none"
                        />
                      </div>
                    )}

                    {editState.preset !== 'Custom' && (
                      <code className="block text-xs text-gray-500 font-mono bg-gray-800/50 rounded px-2 py-1">
                        {PRESETS.find((p) => p.label === editState.preset)?.value || '(empty — CC defaults)'}
                      </code>
                    )}

                    {errors[ember.name] && (
                      <p className="text-xs text-red-400">{errors[ember.name]}</p>
                    )}

                    <div className="flex gap-2">
                      <button
                        onClick={() => savePermissions(ember.name)}
                        disabled={saving[ember.name]}
                        className="px-3 py-1.5 text-xs rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
                      >
                        {saving[ember.name] ? 'Saving…' : 'Save'}
                      </button>
                      <button
                        onClick={() => cancelEdit(ember.name)}
                        disabled={saving[ember.name]}
                        className="px-3 py-1.5 text-xs rounded-lg border border-gray-600 text-gray-300 hover:bg-gray-800 transition-colors disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
