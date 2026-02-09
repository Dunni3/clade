interface SearchBarProps {
  query: string;
  onQueryChange: (q: string) => void;
  placeholder?: string;
  children?: React.ReactNode;
}

export default function SearchBar({ query, onQueryChange, placeholder = 'Search...', children }: SearchBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 mb-4">
      <input
        type="text"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder={placeholder}
        className="flex-1 min-w-[200px] rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
      />
      {children}
    </div>
  );
}
