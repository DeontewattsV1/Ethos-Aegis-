import { EventEmitter } from "../../src/index.js";

type Events = { greet: [name: string] };

const bus = new EventEmitter<Events>();

bus.on("greet", (name) => {
  console.log(`hello, ${name}`);
});

bus.emit("greet", "ada");
bus.emit("greet", "grace");
