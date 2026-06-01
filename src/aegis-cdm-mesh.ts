export type CircuitState = "CLOSED" | "OPEN" | "HALF_OPEN";

export interface AtomicStateStore {
  mutate<TState extends object, TResult>(
    key: string,
    initialState: TState,
    mutation: (state: TState) => { state: TState; result: TResult }
  ): Promise<TResult>;
}

export class MemoryAtomicStateStore implements AtomicStateStore {
  private readonly states = new Map<string, object>();
  private readonly locks = new Map<string, Promise<void>>();

  private async withLock<T>(key: string, fn: () => Promise<T>): Promise<T> {
    // Wait for any existing lock on this key
    const existingLock = this.locks.get(key);
    const waitForUnlock = existingLock ?? Promise.resolve();

    let releaseLock: () => void;
    const acquireLock = new Promise<void>((resolve) => { releaseLock = resolve; });
    this.locks.set(key, acquireLock);

    try {
      await waitForUnlock;
      return await fn();
    } finally {
      this.locks.delete(key);
      releaseLock!();
    }
  }

  async mutate<TState extends object, TResult>(
    key: string,
    initialState: TState,
    mutation: (state: TState) => { state: TState; result: TResult }
  ): Promise<TResult> {
    return this.withLock(key, async () => {
      const current = (this.states.get(key) as TState | undefined) ?? structuredClone(initialState);
      const next = mutation(structuredClone(current));
      this.states.set(key, structuredClone(next.state));
      return next.result;
    });
  }
}

function sortKeys(value: unknown): unknown {
  if (value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map(sortKeys);
  const sorted: Record<string, unknown> = {};
  for (const key of Object.keys(value as Record<string, unknown>).sort()) {
    sorted[key] = sortKeys((value as Record<string, unknown>)[key]);
  }
  return sorted;
}

export function stableHash(value: unknown): string {
  const canonical = JSON.stringify(sortKeys(value));
  let hash = 0x811c9dc5;
  for (let i = 0; i < canonical.length; i++) {
    hash ^= canonical.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}
