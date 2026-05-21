import { EventEmitter } from "../../src/index.js";

type Events = { work: [payload: string] };

const bus = new EventEmitter<Events>();

bus.onError((err, event) => {
  const msg = err instanceof Error ? err.message : String(err);
  console.log(`[err on ${String(event)}] ${msg}`);
});

bus.on("work", (payload) => {
  if (payload === "boom") throw new Error("listener exploded");
  console.log(`processed: ${payload}`);
});

bus.emit("work", "task-1");
bus.emit("work", "boom");
bus.emit("work", "task-3");
