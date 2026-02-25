import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { searchHearth } from '../api/mailbox';
import type { SearchResult } from '../types/mailbox';

interface AdvancedSearchProps {
  open: boolean;
  onClose: () => void;
}

const TYPE_BADGES: Record<string, { label: string; color: string }> = {
  task: { label: 'T', color: 'bg-blue-600' },
  morsel: { label: 'M', color: 'bg-amber-600' },
  card: { label: 'C', color: 'bg-emerald-600' },
};

const TYPE_KEYS = ['task', 'morsel', 'card'] as const;

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

interface GroupedResults {
  type: string;
  label: string;
  results: SearchResult[];
}

function groupResults(
  results: SearchResult[],
  activeTypes: Set<string>
): GroupedResults[] {
  const groups: GroupedResults[] = [];
  for (const type of TYPE_KEYS) {
    if (!activeTypes.has(type)) continue;
    const filtered = results.filter((r) => r.type === type);
    if (filtered.length === 0) continue;
    const label =
      type === 'task' ? 'Tasks' : type === 'morsel' ? 'Morsels' : 'Cards';
    groups.push({ type, label, results: filtered });
  }
  return groups;
}

/** Build a flat list of results across groups for arrow-key navigation */
function flatResults(groups: GroupedResults[]): SearchResult[] {
  return groups.flatMap((g) => g.results);
}

export default function AdvancedSearch({ open, onClose }: AdvancedSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(
    new Set(TYPE_KEYS)
  );
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSearchRef = useRef<string>('');

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setSelectedIndex(0);
      setActiveTypes(new Set(TYPE_KEYS));
      setDateFrom('');
      setDateTo('');
      lastSearchRef.current = '';
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const doSearch = useCallback(
    async (q: string, types: Set<string>, from: string, to: string) => {
      if (!q.trim()) {
        setResults([]);
        return;
      }
      const typesParam =
        types.size === TYPE_KEYS.length
          ? undefined
          : Array.from(types).join(',');
      const searchKey = `${q}|${typesParam}|${from}|${to}`;
      lastSearchRef.current = searchKey;
      setLoading(true);
      try {
        const resp = await searchHearth({
          q,
          types: typesParam,
          limit: 50,
          created_after: from || undefined,
          created_before: to || undefined,
        });
        // Only apply if this is still the latest search
        if (lastSearchRef.current === searchKey) {
          setResults(resp.results);
          setSelectedIndex(0);
        }
      } catch {
        if (lastSearchRef.current === searchKey) {
          setResults([]);
        }
      } finally {
        if (lastSearchRef.current === searchKey) {
          setLoading(false);
        }
      }
    },
    []
  );

  const triggerSearch = useCallback(
    (q: string, types: Set<string>, from: string, to: string) => {
      if (debounceRef.current !== null) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => doSearch(q, types, from, to), 300);
    },
    [doSearch]
  );

  const handleInputChange = (value: string) => {
    setQuery(value);
    triggerSearch(value, activeTypes, dateFrom, dateTo);
  };

  const toggleType = (type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        // Don't allow deselecting all
        if (next.size > 1) next.delete(type);
      } else {
        next.add(type);
      }
      triggerSearch(query, next, dateFrom, dateTo);
      return next;
    });
  };

  const handleDateFromChange = (value: string) => {
    setDateFrom(value);
    triggerSearch(query, activeTypes, value, dateTo);
  };

  const handleDateToChange = (value: string) => {
    setDateTo(value);
    triggerSearch(query, activeTypes, dateFrom, value);
  };

  const groups = groupResults(results, activeTypes);
  const flat = flatResults(groups);

  const handleSelect = (result: SearchResult) => {
    onClose();
    navigate(resultPath(result));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, flat.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && flat[selectedIndex]) {
      handleSelect(flat[selectedIndex]);
    }
  };

  /** Get the flat index for a result within a group */
  const getFlatIndex = (groupIdx: number, resultIdx: number): number => {
    let offset = 0;
    for (let i = 0; i < groupIdx; i++) {
      offset += groups[i].results.length;
    }
    return offset + resultIdx;
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] bg-black/60"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Header: Search input */}
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
            placeholder="Advanced search..."
            className="flex-1 bg-transparent text-gray-100 placeholder-gray-500 outline-none text-base"
          />
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-xs font-mono text-gray-400 bg-gray-800 border border-gray-600 rounded">
            ESC
          </kbd>
        </div>

        {/* Filter row: type chips + date range */}
        <div className="flex flex-wrap items-center gap-3 px-4 py-2.5 border-b border-gray-700/50">
          <div className="flex items-center gap-1.5">
            {TYPE_KEYS.map((type) => {
              const badge = TYPE_BADGES[type];
              const active = activeTypes.has(type);
              const label =
                type === 'task'
                  ? 'Tasks'
                  : type === 'morsel'
                    ? 'Morsels'
                    : 'Cards';
              return (
                <button
                  key={type}
                  onClick={() => toggleType(type)}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                    active
                      ? `${badge.color} text-white`
                      : 'bg-gray-800 text-gray-500 hover:text-gray-300'
                  }`}
                >
                  <span className="font-bold">{badge.label}</span>
                  {label}
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <label className="text-xs text-gray-500">From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => handleDateFromChange(e.target.value)}
              className="bg-gray-800 text-gray-300 text-xs border border-gray-700 rounded px-2 py-1 outline-none focus:border-gray-500 [color-scheme:dark]"
            />
            <label className="text-xs text-gray-500">To</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => handleDateToChange(e.target.value)}
              className="bg-gray-800 text-gray-300 text-xs border border-gray-700 rounded px-2 py-1 outline-none focus:border-gray-500 [color-scheme:dark]"
            />
          </div>
        </div>

        {/* Results area */}
        <div className="max-h-[60vh] overflow-y-auto">
          {loading && (
            <div className="px-4 py-6 text-center text-gray-500 text-sm">
              Searching...
            </div>
          )}
          {!loading && query.trim() && flat.length === 0 && (
            <div className="px-4 py-6 text-center text-gray-500 text-sm">
              No results found.
            </div>
          )}
          {!loading &&
            groups.map((group, groupIdx) => (
              <div key={group.type}>
                {/* Section header */}
                <div className="px-4 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider bg-gray-900/80 sticky top-0 border-b border-gray-800">
                  {group.label} ({group.results.length})
                </div>
                {group.results.map((result, resultIdx) => {
                  const flatIdx = getFlatIndex(groupIdx, resultIdx);
                  const badge = TYPE_BADGES[result.type] || {
                    label: '?',
                    color: 'bg-gray-600',
                  };
                  return (
                    <button
                      key={`${result.type}-${result.id}`}
                      className={`w-full text-left px-4 py-3 flex items-start gap-3 transition-colors ${
                        flatIdx === selectedIndex
                          ? 'bg-indigo-600/20'
                          : 'hover:bg-gray-800'
                      }`}
                      onClick={() => handleSelect(result)}
                      onMouseEnter={() => setSelectedIndex(flatIdx)}
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
                          {result.created_at && (
                            <span className="ml-2 text-gray-600">
                              {result.created_at.slice(0, 10)}
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
