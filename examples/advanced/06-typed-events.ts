import { EventEmitter } from "../../src/index.js";

type AppEvents = {
  login: [user: { id: string; name: string }];
  logout: [user: { id: string }];
  message: [from: string, body: string];
};

const bus = new EventEmitter<AppEvents>();

bus.on("login", (user) => {
  console.log(`login: ${user.name} (${user.id})`);
});

bus.on("message", (from, body) => {
  console.log(`<${from}> ${body}`);
});

bus.on("logout", (user) => {
  console.log(`logout: ${user.id}`);
});

bus.emit("login", { id: "u1", name: "Ada Lovelace" });
bus.emit("message", "u1", "Hello, world.");
bus.emit("logout", { id: "u1" });
