import { describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useAsync } from "./hooks";

/** A promise the test resolves or rejects by hand, to control the order in which requests finish. */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe("useAsync", () => {
  it("starts loading, then gives the data", async () => {
    const d = deferred<string>();
    const { result } = renderHook(() => useAsync(() => d.promise, []));
    expect(result.current).toMatchObject({ loading: true, data: null, error: null });
    await act(async () => d.resolve("hello"));
    expect(result.current).toMatchObject({ loading: false, data: "hello", error: null });
  });

  it("never shows the previous request's data after the dependencies change (no stale data)", async () => {
    const first = deferred<string>(), second = deferred<string>();
    const { result, rerender } = renderHook(({ id }) => useAsync(() => (id === 1 ? first.promise : second.promise), [id]), { initialProps: { id: 1 } });
    await act(async () => first.resolve("one"));
    expect(result.current.data).toBe("one");
    rerender({ id: 2 });
    expect(result.current).toMatchObject({ loading: true, data: null });          // not "one" while "two" is loading
    await act(async () => second.resolve("two"));
    expect(result.current).toMatchObject({ loading: false, data: "two" });
  });

  it("ignores a slow, superseded request that finishes after the newer one", async () => {
    const slow = deferred<string>(), fast = deferred<string>();
    const { result, rerender } = renderHook(({ id }) => useAsync((signal) => { void signal; return id === 1 ? slow.promise : fast.promise; }, [id]), { initialProps: { id: 1 } });
    rerender({ id: 2 });
    await act(async () => fast.resolve("fast"));
    await act(async () => slow.resolve("slow (too late)"));
    expect(result.current.data).toBe("fast");
  });

  it("aborts the previous request's signal when the dependencies change and on unmount", async () => {
    const signals: AbortSignal[] = [];
    const { rerender, unmount } = renderHook(({ id }) => useAsync((s) => { signals.push(s); return new Promise<string>(() => {}); }, [id]), { initialProps: { id: 1 } });
    rerender({ id: 2 });
    expect(signals).toHaveLength(2);
    expect(signals[0]?.aborted).toBe(true);
    expect(signals[1]?.aborted).toBe(false);
    unmount();
    expect(signals[1]?.aborted).toBe(true);
  });

  it("reports an error, and reload runs the request again", async () => {
    let calls = 0;
    const { result } = renderHook(() => useAsync(() => (++calls === 1 ? Promise.reject(new Error("boom")) : Promise.resolve("ok")), []));
    await waitFor(() => expect(result.current.error?.message).toBe("boom"));
    expect(result.current).toMatchObject({ loading: false, data: null });
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.data).toBe("ok"));
    expect(result.current.error).toBeNull();
    expect(calls).toBe(2);
  });

  it("does nothing while disabled, and starts when enabled", async () => {
    let calls = 0;
    const { result, rerender } = renderHook(({ on }) => useAsync(() => { calls++; return Promise.resolve("x"); }, [], on), { initialProps: { on: false } });
    expect(result.current).toMatchObject({ loading: false, data: null, error: null });
    expect(calls).toBe(0);
    rerender({ on: true });
    await waitFor(() => expect(result.current.data).toBe("x"));
    expect(calls).toBe(1);
    rerender({ on: false });
    expect(result.current).toMatchObject({ loading: false, data: null });         // disabled again: no stale data
  });

  it("uses the latest function without refetching when only the function identity changes", async () => {
    let calls = 0;
    const { rerender } = renderHook(({ n }) => useAsync(() => { calls++; return Promise.resolve(n); }, []), { initialProps: { n: 1 } });
    await waitFor(() => expect(calls).toBe(1));
    rerender({ n: 2 });
    rerender({ n: 3 });
    expect(calls).toBe(1);
  });
});
