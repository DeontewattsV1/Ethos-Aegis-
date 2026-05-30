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

  async mutate<TState extends object, TResult>(
    key: string,
    initialState: TState,
    mutation: (state: TState) => { state: TState; result: TResult }
  ): Promise<TResult> {
    const current = (this.states.get(key) as TState | undefined) ?? structuredClone(initialState);
    const next = mutation(structuredClone(current));
    this.states.set(key, structuredClone(next.state));
    return next.result;
  }
}

export function stableHash(value: unknown): string {
  const canonical = JSON.stringify(value, Object.keys(value as Record<string, unknown>).sort());
  let hash = 0x811c9dc5;
  for (let i = 0; i < canonical.length; i++) {
    hash ^= canonical.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}
