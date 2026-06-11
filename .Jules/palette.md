## 2026-06-10 - [REPL Visual Clutter Management]
**Learning:** Developers frequently running interactive scenarios and event emissions in the REPL encounter high visual cognitive load as output accumulates, making it difficult to distinguish between previous and current state.
**Action:** Provide an explicit, low-friction mechanism (.cls) to clear the terminal screen within the REPL session to maintain operational focus.

## 2026-06-11 - [REPL Guidance and Visual Hierarchy]
**Learning:** In terminal-based interactive environments (REPLs), users often lose track of available shortcuts and the active context. Subtle color-coding of the prompt and explicit "shortcut hints" on startup significantly reduce the friction for new users and decrease the likelihood of accidental exits.
**Action:** Color-code the REPL prompt with the brand's primary accent color and display a concise "Shortcut hints" section (Ctrl+C/Ctrl+D) upon session initialization.
