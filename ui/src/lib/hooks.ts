import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/api/client";

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | Error | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Run an async function when `deps` change; the previous request is aborted. `enabled=false` leaves it idle.
 *
 * Every result is stored together with the token of the dependency set that produced it, and only a result whose
 * token matches the current one is returned. So data from a previous request is never shown after the dependencies
 * change (or after the hook is disabled), and state is only ever set from the request's own callbacks.
 */
export function useAsync<T>(fn: (signal: AbortSignal) => Promise<T>, deps: readonly unknown[], enabled = true): AsyncState<T> {
  const [tick, setTick] = useState(0);
  // a new object whenever any dependency changes: identifies "this request"
  // the caller supplies the dependency list (like React's own hooks), so it cannot be an array literal here
  // eslint-disable-next-line react-hooks/exhaustive-deps, react-hooks/use-memo
  const token = useMemo(() => ({}), [...deps, enabled, tick]);
  const [result, setResult] = useState<{ token: object; data: T | null; error: ApiError | Error | null } | null>(null);

  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;       // always call the latest function, without refetching when only its identity changes
  });

  useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    fnRef.current(ctrl.signal).then(
      (data) => {
        if (!ctrl.signal.aborted) setResult({ token, data, error: null });
      },
      (e: unknown) => {
        if (ctrl.signal.aborted || (e as Error)?.name === "AbortError") return;
        setResult({ token, data: null, error: e as Error });
      },
    );
    return () => ctrl.abort();
  }, [token, enabled]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const current = result && result.token === token ? result : null;
  return { data: current?.data ?? null, error: current?.error ?? null, loading: enabled && current === null, reload };
}

export type Theme = "dark" | "light";

function readTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/** Dark = "Obsidian Observatory", light = "Archival Daylight". The choice is remembered when storage works. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(readTheme);
  const toggle = useCallback(() => {
    const next: Theme = readTheme() === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem("pc-theme", next);
    } catch {
      /* storage can be blocked; the theme still switches for this session */
    }
    setTheme(next);
  }, []);
  return [theme, toggle];
}

/**
 * Size of an element, kept current with ResizeObserver. Returns a callback ref (pass it as `ref`), so it also
 * works for an element that is rendered later than the component that owns the hook.
 */
export function useElementSize<T extends HTMLElement>(): [(el: T | null) => void, { width: number; height: number }] {
  const [el, setEl] = useState<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    if (!el) return;
    const update = () => setSize({ width: el.clientWidth, height: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return [setEl, size];
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
