import { useState, useEffect, useCallback } from 'react';

const KEY = 'c2-theme';

function initial(): boolean {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light') return false;
    if (saved === 'dark') return true;
  } catch { /* ignore */ }
  return true;
}

function apply(dark: boolean) {
  document.documentElement.classList.toggle('dark', dark);
  try {
    localStorage.setItem(KEY, dark ? 'dark' : 'light');
  } catch { /* ignore */ }
}

export function useTheme() {
  const [dark, setDark] = useState<boolean>(initial);

  useEffect(() => {
    apply(dark);
  }, [dark]);

  const toggle = useCallback(() => {
    setDark((d) => !d);
  }, []);

  return { dark, toggle };
}
