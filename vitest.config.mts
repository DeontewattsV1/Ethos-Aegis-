import { defineConfig } from 'vitest/config';

const isCI = process.env.CI === 'true';

export default defineConfig({
  test: {
    environment: 'node',
    globals: false,
    include: [
      'test/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}',
      'tests/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}',
      'src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'
    ],
    exclude: ['node_modules/**', 'dist/**', 'coverage/**'],
    passWithNoTests: false,
    reporters: isCI ? ['dot'] : ['default'],
    clearMocks: true,
    restoreMocks: true,
    mockReset: true,
    testTimeout: isCI ? 10_000 : 5_000,
    hookTimeout: isCI ? 10_000 : 5_000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      reportsDirectory: 'coverage',
      exclude: [
        'coverage/**',
        'dist/**',
        'node_modules/**',
        'test/**',
        'tests/**',
        '**/*.d.ts',
        'vitest.config.*'
      ]
    }
  }
});
