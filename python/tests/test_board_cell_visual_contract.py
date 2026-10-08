"""Regression contracts for diagram-inspired defense cells on every 4D board."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "assets" / "brand" / "aegis-4d-video-board.svg"
WEB_BOARD = ROOT / "board.html"
MIRROR = ROOT / "docs" / "4d-immersive" / "index.html"
BRIEF = ROOT / "docs" / "aegis-brief" / "board.html"


def test_readme_animation_uses_distinct_biological_cell_symbols():
    tree = ET.parse(SVG)
    ns = "{http://www.w3.org/2000/svg}"
    defs = tree.getroot().find(ns + "defs")
    assert defs is not None
    for symbol, role in (("cellT", "sentinel"), ("cellG", "adjudicator")):
        matches = [item for item in defs if item.attrib.get("id") == symbol]
        assert len(matches) == 1
        assert matches[0].attrib["data-cell-role"] == role
        assert len(matches[0].findall(".//" + ns + "circle")) >= 9
        assert matches[0].find(ns + "path") is not None
    raw = SVG.read_text(encoding="utf-8")
    assert "animateMotion" in raw
    assert "not a live scanner" in raw.lower()


def test_3d_pages_are_mirrors_with_leukocyte_anatomy_and_scene_controls():
    live = WEB_BOARD.read_text(encoding="utf-8")
    assert live == MIRROR.read_text(encoding="utf-8")
    for token in ("function makeCell(role = 'sentinel')", "nucleusGeo",
                  "pseudopodGeo", "granuleGeo", "leukocytePalette",
                  "role,nucleus", "makeCell(i % 3 === 0 ? 'finality' : 'sentinel')",
                  "OrbitControls", "threatCfg", "scanCfg", "respCfg",
                  "renderer.setAnimationLoop", "LOW-FPS DETECTED"):
        assert token in live, token
    assert "LIVE ENGAGEMENT SIMULATION" not in live


def test_compact_board_uses_leukocyte_shapes_and_preserves_run_controls():
    content = BRIEF.read_text(encoding="utf-8")
    for token in ("function drawMark(id, x, y, s)",
                  "Three interconnected nuclear lobes", "pseudopod",
                  "function frame()", "scanEl", "responseEl"):
        assert token in content, token


def test_reference_diagrams_and_readme_remain_present():
    for asset in ("anatomy_diagram.png", "vitality_upgrade.png", "leukocyte_defense.png"):
        assert (ROOT / "assets" / "brand" / asset).is_file()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "assets/brand/aegis-4d-video-board.svg" in readme
    assert "aegis_header_v2.png" in readme
    assert "Integrated Security Systems — Video Walkthroughs" in readme
