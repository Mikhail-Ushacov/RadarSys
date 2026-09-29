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
  const root = document.documentElement;
  root.classList.add('no-transition');
  void root.offsetHeight;
  root.classList.toggle('dark', dark);
  requestAnimationFrame(() => root.classList.remove('no-transition'));
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
