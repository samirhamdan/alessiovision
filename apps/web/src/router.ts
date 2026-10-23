import { useCallback, useEffect, useState } from "react";

/** Roteamento mínimo pela History API (o nginx devolve index.html para qualquer caminho). */
export function useRoute(): [string, (path: string) => void] {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((next: string) => {
    if (next !== window.location.pathname) window.history.pushState(null, "", next);
    setPath(next);
    window.scrollTo(0, 0);
  }, []);

  return [path, navigate];
}
