/**
 * REPL-friendly walkthrough. Each line is something you could paste into the
 * REPL session opened by `npm run repl`.
 */
import { EventEmitter } from "../../src/index.js";

type Events = {
  hello: [name: string];
  goodbye: [name: string];
};

const bus = new EventEmitter<Events>();

// Step 1 — subscribe
const offHello = bus.on("hello", (name) => console.log(`> hello ${name}`));

// Step 2 — emit
bus.emit("hello", "world");

// Step 3 — once
bus.once("goodbye", (name) => console.log(`> goodbye ${name} (this fires once)`));
bus.emit("goodbye", "world");
bus.emit("goodbye", "world"); // no output

// Step 4 — unsubscribe
offHello();
const notified = bus.emit("hello", "void");
console.log(`> after unsubscribe, listeners notified: ${notified}`);
