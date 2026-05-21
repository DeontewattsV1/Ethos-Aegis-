import { EventEmitter } from "../../src/index.js";

type Events = { tick: [n: number] };

const bus = new EventEmitter<Events>();

let total = 0;
bus.on("tick", (n) => {
  total += n;
});

for (let i = 1; i <= 5; i++) bus.emit("tick", i);

console.log(`sum of ticks: ${total}`);
console.log(`listeners on 'tick': ${bus.listenerCount("tick")}`);
