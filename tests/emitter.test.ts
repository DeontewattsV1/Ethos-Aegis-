import { describe, it, expect, vi } from "vitest";
import { EventEmitter } from "../src/index.js";

type Events = {
  greet: [name: string];
  tick: [n: number];
  ping: [];
  error: [err: Error];
};

describe("EventEmitter", () => {
  it("delivers events to subscribed listeners", () => {
    const bus = new EventEmitter<Events>();
    const spy = vi.fn();
    bus.on("greet", spy);
    bus.emit("greet", "ada");
    expect(spy).toHaveBeenCalledWith("ada");
  });

  it("returns an unsubscribe function from on()", () => {
    const bus = new EventEmitter<Events>();
    const spy = vi.fn();
    const off = bus.on("ping", spy);
    bus.emit("ping");
    off();
    bus.emit("ping");
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("fires once() exactly one time", () => {
    const bus = new EventEmitter<Events>();
    const spy = vi.fn();
    bus.once("ping", spy);
    bus.emit("ping");
    bus.emit("ping");
    bus.emit("ping");
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("supports off() to remove a listener", () => {
    const bus = new EventEmitter<Events>();
    const handler = vi.fn();
    bus.on("ping", handler);
    bus.emit("ping");
    bus.off("ping", handler);
    bus.emit("ping");
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("returns number of listeners notified from emit()", () => {
    const bus = new EventEmitter<Events>();
    bus.on("tick", () => {});
    bus.on("tick", () => {});
    expect(bus.emit("tick", 1)).toBe(2);
    expect(bus.emit("ping")).toBe(0);
  });

  it("routes listener errors to onError handler", () => {
    const bus = new EventEmitter<Events>();
    const errSpy = vi.fn();
    bus.onError(errSpy);
    bus.on("ping", () => {
      throw new Error("boom");
    });
    bus.emit("ping");
    expect(errSpy).toHaveBeenCalledTimes(1);
    const [err, event] = errSpy.mock.calls[0]!;
    expect(err).toBeInstanceOf(Error);
    expect(event).toBe("ping");
  });

  it("rethrows listener errors when no onError handler registered", () => {
    const bus = new EventEmitter<Events>();
    bus.on("ping", () => {
      throw new Error("boom");
    });
    expect(() => bus.emit("ping")).toThrow("boom");
  });

  it("tracks listener counts per event", () => {
    const bus = new EventEmitter<Events>();
    bus.on("tick", () => {});
    bus.on("tick", () => {});
    bus.on("ping", () => {});
    expect(bus.listenerCount("tick")).toBe(2);
    expect(bus.listenerCount("ping")).toBe(1);
    expect(bus.listenerCount("greet")).toBe(0);
  });

  it("removeAllListeners() clears one or all events", () => {
    const bus = new EventEmitter<Events>();
    bus.on("tick", () => {});
    bus.on("ping", () => {});
    bus.removeAllListeners("tick");
    expect(bus.listenerCount("tick")).toBe(0);
    expect(bus.listenerCount("ping")).toBe(1);
    bus.removeAllListeners();
    expect(bus.listenerCount("ping")).toBe(0);
  });
});
