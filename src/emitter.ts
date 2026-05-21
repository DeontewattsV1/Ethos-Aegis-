/**
 * A typed event emitter with subscribe / once / off / emit semantics.
 *
 * Generic over an `Events` map where each key is an event name and each value
 * is the tuple of argument types passed to listeners for that event.
 *
 * Notes on semantics:
 *   - Listeners are stored in a `Set`, so registering the same function reference
 *     twice for the same event is a no-op (it stays a single registration).
 *     This is a deliberate departure from Node's built-in EventEmitter, which
 *     allows duplicate registrations.
 *   - `off()` works for listeners registered via either `on()` or `once()`:
 *     for once-registrations, the original listener is tracked on the internal
 *     wrapper and resolved on removal.
 *   - `emit()` returns the count of listeners invoked, including those whose
 *     callback threw and was routed to an `onError` handler.
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

// Internal marker used to link a once-wrapper back to the user's original
// listener so `off(event, original)` can find and remove it.
const ORIGINAL_LISTENER = Symbol("ldt.originalListener");

type WrappedListener<Args extends unknown[]> = Listener<Args> & {
  [ORIGINAL_LISTENER]?: Listener<Args>;
};

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
    const wrapped: WrappedListener<Events[K]> = (...args) => {
      unsubscribe();
      listener(...args);
    };
    wrapped[ORIGINAL_LISTENER] = listener;
    const unsubscribe = this.on(event, wrapped);
    return unsubscribe;
  }

  /**
   * Remove a previously-registered listener.
   *
   * If the listener was registered via `once()`, the original reference (not
   * the internal wrapper) is still removable here.
   */
  off<K extends keyof Events>(event: K, listener: Listener<Events[K]>): void {
    const set = this.handlers.get(event);
    if (!set) return;
    const direct = listener as Listener<unknown[]>;
    if (set.delete(direct)) {
      if (set.size === 0) this.handlers.delete(event);
      return;
    }
    // Fall back: look for a once() wrapper whose original listener matches.
    for (const candidate of set) {
      const original = (candidate as WrappedListener<unknown[]>)[ORIGINAL_LISTENER];
      if (original === (listener as Listener<unknown[]>)) {
        set.delete(candidate);
        if (set.size === 0) this.handlers.delete(event);
        return;
      }
    }
  }

  /**
   * Emit an event. Returns the number of listeners invoked for this event.
   *
   * A listener that threw is still counted in the return value — it received
   * the event before failing. Without any `onError` handler the first throw
   * propagates out of `emit` (subsequent listeners are not invoked), matching
   * Node's `EventEmitter` semantics. With one or more `onError` handlers
   * registered, listener errors are routed there and the remaining listeners
   * still run.
   */
  emit<K extends keyof Events>(event: K, ...args: Events[K]): number {
    const set = this.handlers.get(event);
    if (!set || set.size === 0) return 0;
    let notified = 0;
    for (const listener of [...set]) {
      notified++;
      try {
        (listener as Listener<Events[K]>)(...args);
      } catch (err) {
        if (this.errorHandlers.size === 0) throw err;
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
