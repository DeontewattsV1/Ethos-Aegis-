# Ethos Aegis 4D Board — Leukocyte Cell Visual Specification

The illustrated defense cells align with the biological metaphors used in the repository's **Leukocyte Defense Framework** diagram (`assets/brand/anatomy_diagram.png`) and **The Vitality Protocol — Upgrade System** diagram (`assets/brand/vitality_upgrade.png`). The original diagrams themselves are unchanged.

## Cell families

| Visual family | Code role | Distinguishing anatomy | Semantic role |
|---|---|---|---|
| Teal / cyan leukocyte | `sentinel` — VanguardProbe / SanitasSwarm | Irregular translucent plasma membrane, short pseudopods, three-lobed violet nucleus, luminous granules | Inspection and purification |
| Gold leukocyte | `finality` — FinalityForge | Warm luminous membrane, three-lobed nucleus, gold cytoplasm and granular inclusions | Adjudication / neutralization animation |
| Other defense cells | 2D board's per-cell palette | Same leukocyte anatomy with soft identity-specific tint | LogosScythe, MnemosyneCache, TaintBeacon, CytokineCommand, other selected cells |

The SVG uses reusable symbols `#cellT` and `#cellG` for its existing SMIL attack/recovery loops. The WebGL board uses shared Three.js geometries to keep rendered cells visually consistent without duplicating heavy meshes for each entity. The same WebGL page is maintained in both `board.html` and `docs/4d-immersive/index.html`. The compact 2D board at `docs/aegis-brief/board.html` uses Canvas-drawn counterparts.

The pipeline strip and query-link interface are unchanged; threat-specific query parameters, orbit/zoom, pause, quality fallback, and response animations continue to operate.

**Interpretation:** The cells are an anatomical-inspired *visual metaphor*, not a live microscope feed or a claim of biological simulation. Engagement counts in the board refer only to its synthetic scenario; it does not perform live host scanning. Vitality levels and authorization must come from actual runtime evidence and security policy, never from colors or animation alone.

## Validation

`python -m pytest python/tests/test_board_cell_visual_contract.py` verifies the SVG cell parts, mirrored WebGL pages, retained scene controls, and diagram links. Inspect the animated SVG in the README and the live WebGL page in a browser with Three.js available to verify appearance and motion.
