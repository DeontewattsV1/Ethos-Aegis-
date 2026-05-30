 <p align="center">
  <img src="./assets/brand/08-documentation-header-banner.svg" alt="Ethos Aegis — sovereign AI integrity defense" width="100%" />
</p>

 # Ethos Aegis &mdash; Brand Identity

Original, civilian, government-grade visual identity for the **Ethos Aegis** sovereign AI integrity defense architecture. Built to feel institutional, doctrinal, and unbreakable while staying intentionally and provably independent of any real military or government insignia.

> **Safety contract:** every mark in this kit is original abstract geometry. No eagles, no flags, no stars, no weapons, no real branch crests, no claim of government affiliation. See [`STYLEGUIDE.md`](./assets/brand/STYLEGUIDE.md) for the full safe-use note.

## Mark library

| File | Purpose | Recommended use |
|---|---|---|
| [`01-primary-emblem.svg`](./assets/brand/01-primary-emblem.svg) | Primary brand emblem (shield aperture + halo ring) | Marketing pages, decks, full-bleed hero |
| [`02-monogram-icon.svg`](./assets/brand/02-monogram-icon.svg) | Compact monogram | Favicon, social avatar, GitHub org icon |
| [`03-wordmark-lockup.svg`](./assets/brand/03-wordmark-lockup.svg) | Horizontal wordmark | Documentation headers, slide titles |
| [`04-circular-seal-style-badge.svg`](./assets/brand/04-circular-seal-style-badge.svg) | Seal-style badge | Authority statements, signatures, footers |
| [`05-mission-patch.svg`](./assets/brand/05-mission-patch.svg) | Mission-patch lockup | Press kit, swag, retro/operator artwork |
| [`06-app-icon.svg`](./assets/brand/06-app-icon.svg) | Application icon | App stores, dock/launcher tiles |
| [`07-reverse-white-mark.svg`](./assets/brand/07-reverse-white-mark.svg) | Reverse / white version | Dark backgrounds, video chyron, dark-mode docs |
| [`08-documentation-header-banner.svg`](./assets/brand/08-documentation-header-banner.svg) | 1800&times;560 documentation header | Top-of-README hero, docs landing pages |
| [`09-field-ready-badge.svg`](./assets/brand/09-field-ready-badge.svg) | "Field ready" status badge | Release announcements, operator-grade docs |

Static preview of all marks together: [`ethos-aegis-preview.png`](./assets/brand/ethos-aegis-preview.png).

## Palette tokens

| Token | Hex | Role |
|---|---|---|
| Obsidian | `#050607` | Deepest background, off-screen edges |
| Matte Black | `#0A0B0D` | Primary background |
| Graphite | `#15181C` | Surface / card background |
| Gunmetal | `#222832` | Elevated surface, divider |
| Smoke | `#687482` | Secondary text, inactive states |
| Steel Blue | `#5E89A8` | Primary accent, active states |
| Cold Blue | `#9FC3D7` | Hover accent, highlights |
| Bone White | `#F2F5F7` | Primary text on dark |
| Signal Red | `#B13A3A` | Alert &mdash; sparing use only |

The canonical source for these tokens is [`assets/brand/manifest.json`](./assets/brand/manifest.json). Pull from there if you wire the palette into a CSS / Tailwind / design-token export.

## Usage rules

1. **Black-on-black hierarchy.** The identity is designed to read against matte black, graphite, obsidian, and smoke. Steel blue is the only persistent accent; signal red is reserved for alert and authority states.
2. **Institutional certainty over decoration.** Controlled spacing, disciplined typography, restrained effects.
3. **Original symbolic language.** Never composite the Ethos Aegis marks with real military seals, eagles, flags, stars, weapons, rank insignia, or department-style crests.
4. **Operational clarity.** Every mark must remain readable at GitHub-header, app-icon, slide, documentation, and social-avatar sizes.
5. **Typography.** Use condensed institutional faces (`Inter Tight`, `Archivo Condensed`, `Saira Condensed`, `Roboto Condensed`) for headings, `IBM Plex Sans` / `Inter` for UI, and `IBM Plex Mono` / `Space Mono` for monospace accents. Do not redistribute font files unless you own the license.

## Files

```
assets/brand/
├── 01-primary-emblem.svg
├── 02-monogram-icon.svg
├── 03-wordmark-lockup.svg
├── 04-circular-seal-style-badge.svg
├── 05-mission-patch.svg
├── 06-app-icon.svg
├── 07-reverse-white-mark.svg
├── 08-documentation-header-banner.svg
├── 09-field-ready-badge.svg
├── ethos-aegis-preview.png   ← combined preview of all marks
├── STYLEGUIDE.md             ← visual principles + palette + safe-use note
├── PROMPTS.md                ← generation prompts (for regenerating consistent assets)
└── manifest.json             ← machine-readable asset list + palette tokens
```

All SVGs include `<title>` and `<desc>` elements with the safe-use note baked in, so screen-readers and downstream consumers can pick up the disclaimer automatically.
