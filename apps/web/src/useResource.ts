import { useCallback, useEffect, useRef, useState } from "react";

/** Carrega dados e, se ``refreshMs`` for informado, recarrega periodicamente. */
export function useResource<T>(load: () => Promise<T>, refreshMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(async () => {
    try {
      const next = await loadRef.current();
      setData(next);
      setError(null);
      setUpdatedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void reload();
    if (!refreshMs) return;
    const timer = window.setInterval(reload, refreshMs);
    return () => window.clearInterval(timer);
  }, [reload, refreshMs]);

  return { data, error, updatedAt, reload };
}
