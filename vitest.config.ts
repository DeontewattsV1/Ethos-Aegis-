import { defineConfig } from "vitest/config";

const isCI = process.env.CI === "true";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    exclude: ["node_modules/**", "dist/**", "coverage/**"],
    environment: "node",
    passWithNoTests: false,
    reporters: isCI ? ["dot"] : ["default"],
    clearMocks: true,
    restoreMocks: true,
    mockReset: true,
    testTimeout: isCI ? 10_000 : 5_000,
    hookTimeout: isCI ? 10_000 : 5_000,
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/index.ts"],
      reporter: ["text", "html", "lcov"],
      thresholds: {
        statements: 80,
        branches: 70,
        functions: 80,
        lines: 80,
      },
    },
  },
});
