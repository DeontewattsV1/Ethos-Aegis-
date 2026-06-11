/**
 * Boots a Node REPL with the library pre-loaded as `emitter` and `EventEmitter`,
 * plus a small set of `.dot` commands that turn the REPL into a quick
 * exploration sandbox: `.demo`, `.scenario`, `.tap`, `.history`, `.reset`.
 *
 * Run with: `npm run repl`
 *
 * Quick start:
 *   ldt> .help                    # list commands
 *   ldt> emitter.on("hello", n => console.log(`hi ${n}`))
 *   ldt> emitter.emit("hello", "ada")
 *   ldt> .scenario subscribe       # run an example end-to-end
 *   ldt> .tap                      # log every future emit
 *   ldt> .history                  # show recent emits
 */
import repl, { type REPLServer } from "node:repl";
import { EventEmitter } from "./src/index.js";

// ─── State ──────────────────────────────────────────────────────────────────
type DemoEvents = {
  hello: [name: string];
  tick: [n: number];
  error: [err: Error];
};

type HistoryEntry = {
  ts: string;
  event: string;
  args: unknown[];
};

const HISTORY_LIMIT = 20;
const history: HistoryEntry[] = [];
let tapEnabled = false;
let emitter = makeEmitter();

function makeEmitter(): EventEmitter<DemoEvents> {
  const instance = new EventEmitter<DemoEvents>();
  // Wrap `emit` so every event is recorded; tap can additionally log live.
  // We use a Proxy so the wrapped function keeps the original method's full
  // generic signature without needing a `as` cast.
  const originalEmit = instance.emit.bind(instance);
  instance.emit = new Proxy(originalEmit, {
    apply(target, thisArg, argArray) {
      const [event, ...rest] = argArray as [keyof DemoEvents, ...unknown[]];
      history.push({ ts: new Date().toISOString(), event: String(event), args: rest });
      if (history.length > HISTORY_LIMIT) history.shift();
      if (tapEnabled) {
        console.log(`[tap] ${String(event)}`, ...rest);
      }
      return Reflect.apply(target, thisArg, argArray);
    },
  });
  return instance;
}

// ─── Scenarios ──────────────────────────────────────────────────────────────
type Scenario = {
  description: string;
  run(em: EventEmitter<DemoEvents>): Promise<void> | void;
};

const scenarios = {
  subscribe: {
    description: "on('hello') + 3 emits — the most basic subscribe loop.",
    run(em) {
      const off = em.on("hello", (name) => { console.log(`  hello, ${name}`); });
      em.emit("hello", "ada");
      em.emit("hello", "grace");
      em.emit("hello", "linus");
      off();
    },
  },
  once: {
    description: "once('tick') fires for the first emit only.",
    run(em) {
      em.once("tick", (n) => { console.log(`  once tick=${n}`); });
      em.emit("tick", 1);
      em.emit("tick", 2);
      em.emit("tick", 3);
    },
  },
  off: {
    description: "on(), then off(), then emit — no listener fires.",
    run(em) {
      const handler = (n: number) => { console.log(`  tick=${n}`); };
      const unsubscribe = em.on("tick", handler);
      em.emit("tick", 1);
      unsubscribe();
      em.emit("tick", 2);
      console.log("  (no second tick logged — unsubscribed)");
    },
  },
  error: {
    description: "onError() captures a thrown listener error and keeps the loop alive.",
    run(em) {
      em.onError((err, event) => {
        console.log(`  caught from '${String(event)}': ${(err as Error).message}`);
      });
      em.on("hello", () => {
        throw new Error("boom");
      });
      em.emit("hello", "ada");
    },
  },
} satisfies Record<string, Scenario>;

const allScenarios: Record<string, Scenario> = {
  ...scenarios,
  all: {
    description: "Run every named scenario in order on a fresh emitter each time.",
    async run() {
      for (const [name, scenario] of Object.entries(scenarios)) {
        console.log(`\n— ${name}: ${scenario.description}`);
        const fresh = new EventEmitter<DemoEvents>();
        // `run()` may be sync (`void`) or async (`Promise<void>`); normalize
        // both so the loop awaits sequentially without misusing `await` on
        // a non-Thenable.
        await Promise.resolve(scenario.run(fresh));
      }
    },
  },
};

// ─── REPL bootstrap ─────────────────────────────────────────────────────────
const STEEL_BLUE = "\x1b[38;2;94;137;168m";
const RESET = "\x1b[0m";

console.log(`${STEEL_BLUE}LIVING DOCS REPL${RESET}`);
console.log("=========================");
console.log("Pre-loaded: `EventEmitter`, `emitter` (Aegis Leukocyte bus)");
console.log("Type `.help` for the full command list.");
console.log(`\n${STEEL_BLUE}Shortcut hints:${RESET}`);
console.log("  Ctrl+C  Abort current expression / Clear line");
console.log("  Ctrl+D  Exit the REPL");
console.log("");

const session: REPLServer = repl.start({
  prompt: `${STEEL_BLUE}ldt>${RESET} `,
  useColors: true,
});
refreshContext(session);

function refreshContext(srv: REPLServer): void {
  srv.context.EventEmitter = EventEmitter;
  srv.context.emitter = emitter;
  srv.context.history = history;
  srv.context.scenarios = allScenarios;
}

session.defineCommand("about", {
  help: "Display template mission and design tokens.",
  action() {
    this.clearBufferedCommand();
    console.log(`\n${STEEL_BLUE}LIVING DOCS TEMPLATE${RESET}`);
    console.log("--------------------------------------------------");
    console.log("Mission: Self-demonstrating, always-current documentation scaffold.");
    console.log("Core: Typed EventEmitter with living snapshot verification.");
    console.log(`\n${STEEL_BLUE}Design Palette (Institutional):${RESET}`);
    console.log("  Obsidian:   #050607");
    console.log("  Steel Blue: #5E89A8 (Primary Accent)");
    console.log("  Bone White: #F2F5F7 (Primary Text)");
    console.log("\nAligned by design.");
    this.displayPrompt();
  },
});

session.defineCommand("demo", {
  help: "Run a short subscribe → emit → log demo on the preloaded emitter.",
  action() {
    this.clearBufferedCommand();
    console.log("Running .demo on the current `emitter`:");
    scenarios.subscribe.run(emitter);
    this.displayPrompt();
  },
});

session.defineCommand("cls", {
  help: "Clear the terminal screen.",
  action() {
    this.clearBufferedCommand();
    console.clear();
    this.displayPrompt();
  },
});

session.defineCommand("scenario", {
  help: "Run a named scenario. Usage: .scenario <name>",
  action(name) {
    this.clearBufferedCommand();
    const key = name.trim();
    const scenario = allScenarios[key];
    if (scenario === undefined) {
      console.log(
        `Unknown scenario "${key}". Available: ${Object.keys(allScenarios).join(", ")}`,
      );
      this.displayPrompt();
      return;
    }
    console.log(`\nRunning scenario "${key}": ${scenario.description}`);
    // Wrap in `new Promise(resolve => resolve(...))` so a synchronous throw
    // inside `scenario.run()` is converted into a rejected Promise. With a
    // plain `Promise.resolve(scenario.run(...))`, a sync throw would escape
    // before the Promise is constructed, leaving the REPL prompt unrestored.
    new Promise<void>((resolve) => {
      resolve(scenario.run(new EventEmitter<DemoEvents>()));
    })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        console.log(`scenario "${key}" threw: ${msg}`);
      })
      .finally(() => {
        this.displayPrompt();
      });
  },
});

session.defineCommand("scenarios", {
  help: "List all available scenarios.",
  action() {
    this.clearBufferedCommand();
    console.log("Available scenarios:");
    for (const [name, scenario] of Object.entries(allScenarios)) {
      console.log(`  ${name.padEnd(10)} ${scenario.description}`);
    }
    this.displayPrompt();
  },
});

session.defineCommand("tap", {
  help: "Toggle live logging of every emit on the preloaded `emitter`.",
  action() {
    this.clearBufferedCommand();
    tapEnabled = !tapEnabled;
    console.log(`tap is now ${tapEnabled ? "ON" : "OFF"}`);
    this.displayPrompt();
  },
});

session.defineCommand("history", {
  help: "Show recent emits on the preloaded `emitter` (most recent last).",
  action() {
    this.clearBufferedCommand();
    if (history.length === 0) {
      console.log("(no emits recorded yet)");
    } else {
      for (const entry of history) {
        console.log(`  ${entry.ts}  ${entry.event}`, ...entry.args);
      }
    }
    this.displayPrompt();
  },
});

session.defineCommand("reset", {
  help: "Discard the preloaded emitter and create a fresh one; clear history.",
  action() {
    this.clearBufferedCommand();
    emitter = makeEmitter();
    history.length = 0;
    refreshContext(session);
    console.log("emitter and history reset.");
    this.displayPrompt();
  },
});
