import { useEffect } from 'react';

export function useDocumentTitle(title: string | undefined) {
  useEffect(() => {
    const prev = document.title;
    if (title) document.title = `${title} | The Hearth`;
    return () => { document.title = prev; };
  }, [title]);
}
