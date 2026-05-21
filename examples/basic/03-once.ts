import { EventEmitter } from "../../src/index.js";

type Events = { ready: [] };

const bus = new EventEmitter<Events>();

let calls = 0;
bus.once("ready", () => {
  calls++;
  console.log("ready handler fired");
});

bus.emit("ready");
bus.emit("ready");
bus.emit("ready");

console.log(`handler fired ${calls} time(s)`);
