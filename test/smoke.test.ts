import { describe, expect, it } from 'vitest';

describe('vitest ci smoke test', () => {
  it('executes deterministic test tooling', () => {
    expect({ ready: true, runner: 'vitest' }).toEqual({
      ready: true,
      runner: 'vitest'
    });
  });
});
