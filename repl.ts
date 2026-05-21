/**
 * Boots a Node REPL with the library pre-loaded as `emitter` and `EventEmitter`.
 *
 * Run with: `npm run repl`
 *
 * Try:
 *   emitter.on("hello", (name) => console.log(`hi ${name}`))
 *   emitter.emit("hello", "ada")
 */
import repl from "node:repl";
import { EventEmitter } from "./src/index.js";

type DemoEvents = {
  hello: [name: string];
  tick: [n: number];
  error: [err: Error];
};

const emitter = new EventEmitter<DemoEvents>();

console.log("living-docs-template REPL");
console.log("=========================");
console.log("Available: `EventEmitter`, `emitter` (preconfigured DemoEvents instance)");
console.log("Try: emitter.on('hello', n => console.log(`hi ${n}`)); emitter.emit('hello', 'ada')");
console.log("");

const session = repl.start({ prompt: "ldt> ", useColors: true });
session.context.EventEmitter = EventEmitter;
session.context.emitter = emitter;
