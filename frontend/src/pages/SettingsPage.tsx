import { useState } from 'react';
import { useAuthStore } from '../store/authStore';

const IDENTITIES = [
  { value: 'ian', label: 'Ian' },
  { value: 'doot', label: 'Doot' },
  { value: 'oppy', label: 'Oppy' },
  { value: 'jerry', label: 'Jerry' },
];

export default function SettingsPage() {
  const { apiKey, brotherName, setAuth, clearAuth } = useAuthStore();
  const [keyInput, setKeyInput] = useState(apiKey || '');
  const [nameInput, setNameInput] = useState(brotherName || '');
  const [saved, setSaved] = useState(false);

  function handleSave() {
    if (!keyInput.trim() || !nameInput) return;
    setAuth(keyInput.trim(), nameInput);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Settings</h1>
      <div className="rounded-xl border border-gray-700 bg-gray-900 p-6 space-y-4 max-w-md">
        <div className="text-sm text-gray-400 space-y-1">
          <p>First, accept the self-signed certificate by visiting the API directly:</p>
          <a
            href="https://54.84.119.14/api/v1/unread"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-400 underline break-all"
          >
            https://54.84.119.14/api/v1/unread
          </a>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Who are you?</label>
          <select
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200"
          >
            <option value="">Select...</option>
            {IDENTITIES.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">API Key</label>
          <input
            type="password"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder="Enter your API key"
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
          />
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleSave}
            disabled={!keyInput.trim() || !nameInput}
            className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
          >
            Save
          </button>
          {apiKey && (
            <button
              onClick={clearAuth}
              className="px-4 py-2 text-sm rounded-lg border border-gray-600 text-gray-300 hover:bg-gray-800 transition-colors"
            >
              Sign Out
            </button>
          )}
        </div>
        {saved && <p className="text-sm text-emerald-400">Saved!</p>}
      </div>
    </div>
  );
}
