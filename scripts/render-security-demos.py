"""Execute the local demo commands and render their stdout into branded video.

Requires Pillow and ffmpeg. Reveal timing is editorial; transcripts are unedited.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demos"
BG, PANEL, BORDER = "#050607", "#15181C", "#222832"
WHITE, BLUE, DIM = "#F2F5F7", "#9FC3D7", "#687482"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
TITLES = {"toolkit": "Five tools. One evidence format.", "immune": "AI immune cells in action.",
          "veriflow": "Reason from schema and evidence."}
FPS = 8


def font(size: int, mono: bool = False, bold: bool = False):
    name = "DejaVuSansMono" if mono else "DejaVuSans"
    return ImageFont.truetype(str(FONT_DIR / (name + ("-Bold" if bold else "") + ".ttf")), size)


def draw_frame(title: str, lines: list[str], scene: int, scenes: int, progress: float) -> Image.Image:
    canvas = Image.new("RGB", (1280, 720), BG)
    draw = ImageDraw.Draw(canvas)
    for x in range(0, 1280, 40):
        draw.line((x, 0, x, 720), fill="#0C1014")
    for y in range(0, 720, 40):
        draw.line((0, y, 1280, y), fill="#0C1014")
    draw.rounded_rectangle((40, 32, 102, 94), radius=13, fill=PANEL, outline="#5E89A8", width=2)
    draw.text((49, 49), "EA", font=font(27, bold=True), fill=WHITE)
    draw.text((122, 33), "ETHOS AEGIS", font=font(30, bold=True), fill=WHITE)
    draw.text((124, 73), "SOVEREIGN AI IMMUNE ARCHITECTURE", font=font(14), fill=BLUE)
    draw.text((850, 44), "DEONTE WATTS / LOCAL WALKTHROUGH", font=font(13), fill=DIM)
    draw.text((46, 124), title, font=font(32, bold=True), fill=WHITE)
    draw.text((48, 170), "SYNTHETIC INPUTS  /  ACTUAL EXECUTED OUTPUT  /  NO EXTERNAL SCANS", font=font(13, mono=True), fill=BLUE)
    draw.rounded_rectangle((40, 207, 1240, 643), radius=14, fill=PANEL, outline=BORDER, width=2)
    for i, color in enumerate(["#687482", "#5E89A8", "#9FC3D7"]):
        draw.ellipse((60+i*21, 225, 69+i*21, 234), fill=color)
    draw.text((150, 220), f"Captured stdout  |  scene {scene+1}/{scenes}", font=font(13, mono=True), fill=DIM)
    y = 258
    for line in lines:
        color = BLUE if line.startswith("[") or line.startswith("$") else WHITE
        draw.text((66, y), line, font=font(18, mono=True), fill=color)
        y += 26
    draw.line((48, 668, 1232, 668), fill=BORDER, width=3)
    draw.line((48, 668, 48+int(1184*progress), 668), fill="#5E89A8", width=3)
    draw.text((48, 684), "Detect. Explain. Gate.", font=font(14), fill=BLUE)
    draw.text((650, 685), "Rendered from stdout; reveal timing is not a benchmark.", font=font(12), fill=DIM)
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "ethos-aegis.demo-recordings.v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                "author": "Deonte Watts", "input": "synthetic", "method": "actual stdout rendered progressively",
                "upstream_tools_executed": False, "recordings": []}
    for scenario, title in TITLES.items():
        args = [sys.executable, "-m", "ethos_aegis.security_toolkit", "demo", "--scenario", scenario]
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "python")
        result = subprocess.run(args, cwd=ROOT, env=environment, capture_output=True, text=True, check=True, timeout=30)
        transcript = result.stdout
        (OUT / f"{scenario}.txt").write_text(transcript, encoding="utf-8")
        blocks = transcript.rstrip().split("\n\n")
        scenes = [[f"$ python -m ethos_aegis.security_toolkit demo --scenario {scenario}"]]
        for block in blocks:
            wrapped = [piece for line in block.splitlines() for piece in textwrap.wrap(line, width=102, replace_whitespace=False) or [""]]
            scenes.extend(wrapped[i:i+13] for i in range(0, len(wrapped), 13))
        preview_frames = []
        with tempfile.TemporaryDirectory(prefix="aegis-video-") as folder:
            temp = Path(folder)
            frame_index = 0
            for index, lines in enumerate(scenes):
                for tick in range(FPS*4):
                    visible = min(len(lines), 1 + tick//4)
                    progress = (index + tick/(FPS*4)) / len(scenes)
                    frame = draw_frame(title, lines[:visible], index, len(scenes), progress)
                    frame.save(temp / f"{frame_index:05d}.png")
                    if tick in {8, 24}:
                        preview_frames.append(frame.resize((640, 360)).convert("P", palette=Image.Palette.ADAPTIVE, colors=96))
                    frame_index += 1
            mp4 = OUT / f"{scenario}.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(temp / "%05d.png"),
                            "-c:v", "libx264", "-preset", "fast", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
                           check=True, timeout=60)
        gif = OUT / f"{scenario}-preview.gif"
        preview_frames[0].save(gif, save_all=True, append_images=preview_frames[1:], duration=1200, loop=0, optimize=True)
        poster = OUT / f"{scenario}-poster.png"
        draw_frame(title, scenes[min(2, len(scenes)-1)], min(2, len(scenes)-1), len(scenes), 0.3).save(poster)
        files = [OUT/f"{scenario}.txt", mp4, gif, poster]
        manifest["recordings"].append({"scenario": scenario, "command": f"python -m ethos_aegis.security_toolkit demo --scenario {scenario}",
                                       "duration_seconds": frame_index/FPS, "files": {p.name: {"bytes": p.stat().st_size,
                                       "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}})
        print(f"Rendered {scenario}: {frame_index/FPS:.0f}s, {mp4.stat().st_size:,} bytes", flush=True)
    (OUT/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")


if __name__ == "__main__":
    main()
