import type { ReactNode } from 'react';

// Matches http(s) URLs — handles paths, query strings, fragments, and parentheses.
// Avoids trailing punctuation that's likely sentence-ending (.,;:!?) unless inside parens.
const URL_REGEX =
  /https?:\/\/[^\s<>\"'`]+[^\s<>\"'`.,;:!?)}\]]/g;

/**
 * Takes a string and returns an array of ReactNodes where URLs are wrapped
 * in clickable <a> tags that open in a new tab.
 */
export function linkify(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  // Reset regex state
  URL_REGEX.lastIndex = 0;

  while ((match = URL_REGEX.exec(text)) !== null) {
    const url = match[0];
    const start = match.index;

    // Add text before the URL
    if (start > lastIndex) {
      parts.push(text.slice(lastIndex, start));
    }

    parts.push(
      <a
        key={start}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2"
        onClick={(e) => e.stopPropagation()}
      >
        {url}
      </a>
    );

    lastIndex = start + url.length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : [text];
}

/**
 * Component that renders text with auto-detected URLs as clickable links.
 */
export default function Linkify({ children }: { children: string }) {
  return <>{linkify(children)}</>;
}
