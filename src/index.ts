/**
 * living-docs-template public API.
 *
 * The library is intentionally tiny: a typed `EventEmitter` is the entire
 * subject. Examples in `examples/` drive the README via region markers.
 */
export { EventEmitter } from "./emitter.js";
export type { EventMap, Listener, Unsubscribe } from "./emitter.js";
