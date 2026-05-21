/**
 * A typed event emitter with subscribe / once / off / emit semantics.
 *
 * Generic over an `Events` map where each key is an event name and each value
 * is the tuple of argument types passed to listeners for that event.
 *
 * @example
 * type AppEvents = { login: [user: string]; error: [err: Error] };
 * const bus = new EventEmitter<AppEvents>();
 * bus.on("login", (user) => console.log(`hi ${user}`));
 * bus.emit("login", "ada");
 */
export type EventMap = Record<string, unknown[]>;

export type Listener<Args extends unknown[]> = (...args: Args) => void;

export type Unsubscribe = () => void;

export class EventEmitter<Events extends EventMap> {
  private readonly handlers = new Map<keyof Events, Set<Listener<unknown[]>>>();
  private readonly errorHandlers = new Set<(err: unknown, event: keyof Events) => void>();

  /** Subscribe to an event. Returns an unsubscribe function. */
  on<K extends keyof Events>(event: K, listener: Listener<Events[K]>): Unsubscribe {
    const set = this.handlers.get(event) ?? new Set<Listener<unknown[]>>();
    set.add(listener as Listener<unknown[]>);
    this.handlers.set(event, set);
    return () => this.off(event, listener);
  }

  /** Subscribe to an event for exactly one emission. */
  once<K extends keyof Events>(event: K, listener: Listener<Events[K]>): Unsubscribe {
    const wrapped: Listener<Events[K]> = (...args) => {
      unsubscribe();
      listener(...args);
    };
    const unsubscribe = this.on(event, wrapped);
    return unsubscribe;
  }

  /** Remove a previously-registered listener. */
  off<K extends keyof Events>(event: K, listener: Listener<Events[K]>): void {
    const set = this.handlers.get(event);
    if (!set) return;
    set.delete(listener as Listener<unknown[]>);
    if (set.size === 0) this.handlers.delete(event);
  }

  /** Emit an event. Returns the number of listeners notified. */
  emit<K extends keyof Events>(event: K, ...args: Events[K]): number {
    const set = this.handlers.get(event);
    if (!set || set.size === 0) return 0;
    let notified = 0;
    for (const listener of [...set]) {
      try {
        (listener as Listener<Events[K]>)(...args);
        notified++;
      } catch (err) {
        if (this.errorHandlers.size === 0) {
          throw err;
        }
        for (const eh of this.errorHandlers) eh(err, event);
      }
    }
    return notified;
  }

  /** Register a global error handler. Errors thrown by listeners are routed here. */
  onError(handler: (err: unknown, event: keyof Events) => void): Unsubscribe {
    this.errorHandlers.add(handler);
    return () => {
      this.errorHandlers.delete(handler);
    };
  }

  /** Count listeners currently registered for an event. */
  listenerCount<K extends keyof Events>(event: K): number {
    return this.handlers.get(event)?.size ?? 0;
  }

  /** Remove all listeners, optionally scoped to one event. */
  removeAllListeners<K extends keyof Events>(event?: K): void {
    if (event === undefined) {
      this.handlers.clear();
      return;
    }
    this.handlers.delete(event);
  }
}
