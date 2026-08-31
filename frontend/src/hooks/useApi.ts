/**
 * useApi — minimal data-fetching hook with loading/error state and
 * cancellation safety. Falls back to explicit error rendering; pages
 * decide how to present empty vs error states.
 */
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../lib/api/client";

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
  reload: () => void;
}

export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof ApiError ? e
            : new ApiError(0, "unknown_error", "An unexpected error occurred."));
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, loading, error, reload };
}
