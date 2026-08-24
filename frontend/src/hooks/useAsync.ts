import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | undefined;
  loading: boolean;
  error: unknown;
  /**
   * Whether {@link error} is set. `error` is `unknown`, and `unknown && <JSX/>` is not a
   * valid ReactNode, so every conditional render would otherwise need its own coercion.
   */
  failed: boolean;
  /** Run it again — after a failure, or to pick up a change made elsewhere. */
  reload: () => void;
  /** Replace the data locally, for responses that already carry the next state. */
  setData: (next: T) => void;
}

/**
 * Load something once, and again on demand.
 *
 * Deliberately not a cache. Almost every screen here reads a resource the backend
 * recomputes per request — the skill dashboard is rebuilt from scratch on every call —
 * so a stale-while-revalidate layer would mostly add a way to show numbers that are
 * quietly out of date.
 *
 * `deps` behaves like an effect dependency list: change it and the request re-runs.
 */
export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
): AsyncState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);

  // Keep the latest loader without making it a dependency: callers pass an inline
  // arrow function, which is a new value on every render and would loop forever.
  // Updated in an effect rather than during render, and declared BEFORE the effect that
  // uses it so it is already current by the time that one runs.
  const loaderRef = useRef(loader);
  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    const controller = new AbortController();
    let live = true;

    setLoading(true);
    setError(null);

    loaderRef.current(controller.signal)
      .then((result) => {
        if (!live) return;
        setData(result);
      })
      .catch((cause: unknown) => {
        // An abort is this effect cleaning up after itself, not a failure to report.
        if (!live || controller.signal.aborted) return;
        setError(cause);
      })
      .finally(() => {
        if (live) setLoading(false);
      });

    return () => {
      live = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return { data, loading, error, failed: error != null, reload, setData };
}

/**
 * The mutation counterpart: run on demand, expose whether it is in flight.
 * Used by every form and every action button.
 */
export function useAction<Args extends unknown[], T>(
  action: (...args: Args) => Promise<T>,
): {
  run: (...args: Args) => Promise<T | undefined>;
  running: boolean;
  error: unknown;
  /** See {@link AsyncState.failed}. */
  failed: boolean;
  clearError: () => void;
} {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const actionRef = useRef(action);
  useEffect(() => {
    actionRef.current = action;
  });

  const run = useCallback(async (...args: Args) => {
    setRunning(true);
    setError(null);
    try {
      return await actionRef.current(...args);
    } catch (cause) {
      setError(cause);
      return undefined;
    } finally {
      setRunning(false);
    }
  }, []);

  return {
    run,
    running,
    error,
    failed: error != null,
    clearError: useCallback(() => setError(null), []),
  };
}
