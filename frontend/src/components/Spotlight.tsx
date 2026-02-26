import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { searchHearth } from '../api/mailbox';
import type { SearchResult } from '../types/mailbox';

interface SpotlightProps {
  open: boolean;
  onClose: () => void;
}

const TYPE_BADGES: Record<string, { label: string; color: string }> = {
  task: { label: 'T', color: 'bg-blue-600' },
  morsel: { label: 'M', color: 'bg-amber-600' },
  card: { label: 'C', color: 'bg-emerald-600' },
};

function resultPath(result: SearchResult): string {
  switch (result.type) {
    case 'task':
      return `/tasks/${result.id}`;
    case 'morsel':
      return `/morsels/${result.id}`;
    case 'card':
      return `/board/cards/${result.id}`;
    default:
      return '/';
  }
}

export default function Spotlight({ open, onClose }: SpotlightProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      // Parse filter prefixes: "task:deploy" -> type=task, query=deploy
      let actualQuery = q.trim();
      let types: string | undefined;
      const prefixMatch = actualQuery.match(/^(task|morsel|card):\s*(.*)/i);
      if (prefixMatch) {
        types = prefixMatch[1].toLowerCase();
        actualQuery = prefixMatch[2].trim();
      }
      if (!actualQuery) {
        setResults([]);
        setLoading(false);
        return;
      }
      const resp = await searchHearth({ q: actualQuery, types, limit: 20 });
      setResults(resp.results);
      setSelectedIndex(0);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInputChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current !== null) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 300);
  };

  const handleSelect = (result: SearchResult) => {
    onClose();
    navigate(resultPath(result));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      // Quick-jump: #t123 → task, #m123 → morsel, #c123 → card
      const jumpMatch = query.trim().match(/^#([tmc])(\d+)$/i);
      if (jumpMatch) {
        const typeMap: Record<string, string> = { t: '/tasks/', m: '/morsels/', c: '/board/cards/' };
        onClose();
        navigate(typeMap[jumpMatch[1].toLowerCase()] + jumpMatch[2]);
      } else if (results[selectedIndex]) {
        handleSelect(results[selectedIndex]);
      }
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/60"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-700">
          <svg
            className="w-5 h-5 text-gray-400 shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search tasks, morsels, cards..."
            className="flex-1 bg-transparent text-gray-100 placeholder-gray-500 outline-none text-base"
          />
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-xs font-mono text-gray-400 bg-gray-800 border border-gray-600 rounded">
            ESC
          </kbd>
        </div>
        <div className="px-4 py-1.5 text-xs text-gray-500 border-b border-gray-700/50">
          Prefix with task:, morsel:, or card: to filter. Jump with #t123, #m123, #c123
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto">
          {loading && (
            <div className="px-4 py-6 text-center text-gray-500 text-sm">
              Searching...
            </div>
          )}
          {!loading && query.trim() && results.length === 0 && (
            <div className="px-4 py-6 text-center text-gray-500 text-sm">
              No results found.
            </div>
          )}
          {!loading &&
            results.map((result, i) => {
              const badge = TYPE_BADGES[result.type] || {
                label: '?',
                color: 'bg-gray-600',
              };
              return (
                <button
                  key={`${result.type}-${result.id}`}
                  className={`w-full text-left px-4 py-3 flex items-start gap-3 transition-colors ${
                    i === selectedIndex
                      ? 'bg-indigo-600/20'
                      : 'hover:bg-gray-800'
                  }`}
                  onClick={() => handleSelect(result)}
                  onMouseEnter={() => setSelectedIndex(i)}
                >
                  <span
                    className={`${badge.color} text-white text-xs font-bold w-6 h-6 rounded flex items-center justify-center shrink-0 mt-0.5`}
                  >
                    {badge.label}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-200 truncate">
                      #{result.id} {result.title}
                    </div>
                    <div
                      className="text-xs text-gray-400 mt-0.5 line-clamp-2 [&_mark]:bg-yellow-500/30 [&_mark]:text-yellow-200 [&_mark]:rounded [&_mark]:px-0.5"
                      dangerouslySetInnerHTML={{ __html: result.snippet }}
                    />
                    <div className="text-xs text-gray-500 mt-1">
                      {result.status && (
                        <span className="mr-2">{result.status}</span>
                      )}
                      {result.col && (
                        <span className="mr-2">{result.col}</span>
                      )}
                      {result.assignee && (
                        <span className="mr-2">@{result.assignee}</span>
                      )}
                      {result.creator && <span>by {result.creator}</span>}
                    </div>
                  </div>
                </button>
              );
            })}
        </div>
      </div>
    </div>
  );
}
