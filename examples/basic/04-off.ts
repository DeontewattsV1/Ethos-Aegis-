import { EventEmitter } from "../../src/index.js";

type Events = { ping: [] };

const bus = new EventEmitter<Events>();

const handler = () => console.log("pong");

const unsubscribe = bus.on("ping", handler);

bus.emit("ping");
bus.emit("ping");

unsubscribe();

const notified = bus.emit("ping");
console.log(`listeners notified after unsubscribe: ${notified}`);
