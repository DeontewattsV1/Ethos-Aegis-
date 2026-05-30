import { describe, expect, it } from "vitest";

import { MemoryAtomicStateStore, stableHash } from "../src/index.js";

describe("CDM mesh state primitives", () => {
  it("mutates shared state by key", async () => {
    const store = new MemoryAtomicStateStore();

    const first = await store.mutate("agent-alpha", { count: 0 }, (state) => ({
      state: { count: state.count + 1 },
      result: state.count + 1,
    }));

    const second = await store.mutate("agent-alpha", { count: 0 }, (state) => ({
      state: { count: state.count + 1 },
      result: state.count + 1,
    }));

    expect(first).toBe(1);
    expect(second).toBe(2);
  });

  it("isolates state by key", async () => {
    const store = new MemoryAtomicStateStore();

    await store.mutate("agent-alpha", { count: 0 }, (state) => ({
      state: { count: state.count + 1 },
      result: state.count + 1,
    }));

    const beta = await store.mutate("agent-beta", { count: 0 }, (state) => ({
      state: { count: state.count + 1 },
      result: state.count + 1,
    }));

    expect(beta).toBe(1);
  });

  it("creates stable fingerprints for equivalent root objects", () => {
    expect(stableHash({ traceId: "t-1", agentId: "a-1" })).toBe(
      stableHash({ agentId: "a-1", traceId: "t-1" })
    );
  });
});
