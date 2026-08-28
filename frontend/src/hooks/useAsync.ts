import { useCallback, useEffect, useRef, useState, useId } from 'react';

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

import { useQuery, useQueryClient } from '@tanstack/react-query';

/**
 * Load something once, and again on demand.
 * Refactored to use React Query under the hood for better request lifecycle management,
 * while maintaining the legacy API signature.
 */
export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
): AsyncState<T> {
  const queryClient = useQueryClient();
  const hookId = useId(); // Ensure queries from different useAsync calls don't collide on identical deps

  const loaderRef = useRef(loader);
  useEffect(() => {
    loaderRef.current = loader;
  });

  const queryKey = [hookId, ...deps];

  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => loaderRef.current(signal),
  });

  const reload = useCallback(() => {
    query.refetch();
  }, [query]);

  const setData = useCallback((next: T) => {
    queryClient.setQueryData(queryKey, next);
  }, [queryClient, queryKey]);

  return {
    data: query.data,
    loading: query.isLoading,
    error: query.error,
    failed: query.isError,
    reload,
    setData
  };
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
