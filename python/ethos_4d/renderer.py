"""
FourDRenderer — Terminal-native 4D immersive visualization for ETHOS-AEGIS.

Renders the ethical spacetime manifold as:
  1. ASCII hypercube projection (3D snapshot with T encoded as color/intensity)
  2. Animated task world-line traces (live terminal updates)
  3. Ethical heatmap across the state × node-type grid
  4. Temporal waveform of ethical load over simulation ticks

No external display required — pure terminal art with ANSI 256-color.
"""

from __future__ import annotations

import math
import sys
import time
from typing import Optional

from .spacetime import (
    EthosSpacetime,
    SpacetimeCoordinate,
    TASK_STATE_ORDINAL,
    NODE_TYPE_ORDINAL,
    ETHICAL_WEIGHT,
)

# ─── ANSI color palette ─────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

def fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"

def bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"

# Scientific color scale: blue (safe) → green → yellow → red (critical)
def ethical_color(z: float) -> str:
    """Map z in [0,1] to a blue→red thermal color."""
    r = int(z * 255)
    g = int(math.sin(z * math.pi) * 180)
    b = int((1 - z) * 255)
    return fg(r, g, b)

STATE_SYMBOLS = {
    "QUEUED":         "○",
    "VALIDATED":      "◎",
    "ETHICAL_CHECK":  "⬡",
    "PLANNED":        "◆",
    "ASSIGNED_AGENT": "▲",
    "EXECUTING":      "◉",
    "REVIEW":         "⬢",
    "COMMITTED":      "★",
    "PUBLISHED":      "✦",
    "ARCHIVED":       "□",
    "FAILED":         "✖",
}

NODE_COLORS: dict[str, tuple[int,int,int]] = {
    "Governance":    (180, 80,  255),
    "System":        (80,  180, 255),
    "Agent":         (80,  255, 160),
    "Workflow":      (255, 200, 80),
    "Theory":        (255, 120, 80),
    "Task":          (160, 160, 255),
    "Signal":        (80,  255, 255),
    "Interface":     (255, 80,  180),
    "ComputeLayer":  (140, 255, 140),
    "SecurityLayer": (255, 80,  80),
}


class FourDRenderer:
    """Renders the ETHOS-AEGIS 4D spacetime to terminal."""

    def __init__(self, spacetime: EthosSpacetime, width: int = 80) -> None:
        self.st = spacetime
        self.width = width

    # ── 1. Header banner ─────────────────────────────────────────────────
    def banner(self) -> None:
        w = self.width
        print(fg(80, 200, 255) + BOLD + "╔" + "═" * (w - 2) + "╗" + RESET)
        title = "ETHOS-AEGIS · 4D IMMERSIVE VISUAL TEST MODULE"
        pad = (w - 2 - len(title)) // 2
        print(fg(80, 200, 255) + BOLD + "║" + " " * pad + fg(255,255,100) +
              title + fg(80,200,255) + " " * (w-2-pad-len(title)) + "║" + RESET)
        sub = "Ethical Spacetime Manifold Renderer  v1.0.0  [4D: X·Y·Z·T]"
        pad2 = (w - 2 - len(sub)) // 2
        print(fg(80, 200, 255) + "║" + " " * pad2 + fg(160,160,160) +
              sub + fg(80,200,255) + " " * (w-2-pad2-len(sub)) + "║" + RESET)
        print(fg(80, 200, 255) + BOLD + "╚" + "═" * (w - 2) + "╝" + RESET)

    # ── 2. Ethical heatmap ───────────────────────────────────────────────
    def ethical_heatmap(self) -> None:
        """2D heatmap: rows=TaskState, cols=NodeType, cell=ethical weight."""
        states = list(TASK_STATE_ORDINAL.keys())
        nodes  = list(NODE_TYPE_ORDINAL.keys())

        print(f"\n{BOLD}{fg(200,255,200)}  ⬡ ETHICAL WEIGHT HEATMAP  (TaskState × NodeType){RESET}")
        print(fg(100,100,100) + "  " + "  ".join(f"{n[:4]:>4}" for n in nodes) + RESET)

        for state in states:
            z_base = ETHICAL_WEIGHT[state]
            sym    = STATE_SYMBOLS[state]
            row    = f"{fg(200,200,200)}{state[:14]:<14}{RESET} "
            for node in nodes:
                # Node type slightly modulates ethical weight
                node_idx = NODE_TYPE_ORDINAL[node]
                z = min(1.0, z_base * (1.0 + node_idx * 0.02))
                block = "██"
                row += ethical_color(z) + block + RESET + " "
            row += f" {ethical_color(z_base)}{sym}{RESET} {fg(160,160,160)}{z_base:.2f}{RESET}"
            print(row)

        print()
        # Legend
        print(f"  {fg(0,0,255)}██{RESET} safe (0.0)  →  " +
              f"{fg(0,200,0)}██{RESET} moderate  →  " +
              f"{fg(255,165,0)}██{RESET} elevated  →  " +
              f"{fg(255,0,0)}██{RESET} critical (1.0)")

    # ── 3. World-line traces ─────────────────────────────────────────────
    def world_lines(self) -> None:
        """Print each task's trajectory through 4D spacetime."""
        lines = self.st.world_lines
        if not lines:
            print(fg(200,100,100) + "  No world-lines yet. Run a simulation first." + RESET)
            return

        print(f"\n{BOLD}{fg(255,200,80)}  🌌 TASK WORLD-LINES (4D Trajectories){RESET}")
        print(fg(100,100,100) + "  Task ID          │ X(node) │ Y(state) │ Z(ethics) │ T(tick) │ Arc-Len │ Ethical-∫" + RESET)
        print(fg(60,60,60) + "  " + "─" * 85 + RESET)

        for task_id, wl in lines.items():
            arc = wl.arc_length()
            ei  = wl.ethical_integral()
            last = wl.coordinates[-1]
            nc  = NODE_COLORS.get(last.node_type, (200,200,200))
            print(
                f"  {fg(*nc)}{task_id[:16]:<16}{RESET} │"
                f" {fg(180,180,255)}{last.x:>7.1f}{RESET} │"
                f" {fg(180,255,180)}{last.y:>8.1f}{RESET} │"
                f" {ethical_color(last.z)}{last.z:>9.3f}{RESET} │"
                f" {fg(200,200,100)}{last.t:>7.3f}{RESET} │"
                f" {fg(200,160,255)}{arc:>7.3f}{RESET} │"
                f" {ethical_color(ei if ei <= 1.0 else 1.0)}{ei:>10.6f}{RESET}"
            )

    # ── 4. Hypercube projection ──────────────────────────────────────────
    def hypercube(self, tick: float = 0.0) -> None:
        """
        Project the 4D ethical hypercube onto 2D terminal via
        oblique isometric projection. T encoded as character density.
        """
        print(f"\n{BOLD}{fg(100,200,255)}  ◈ 4D HYPERCUBE PROJECTION  (T={tick:.2f}){RESET}")

        grid_w, grid_h = 60, 18
        canvas = [[" "] * grid_w for _ in range(grid_h)]

        # 4D unit hypercube vertices: all combos of (0/1)^4
        vertices_4d = [(x, y, z, t) for x in (0,1) for y in (0,1)
                       for z in (0,1) for t in (0,1)]

        def project(vx, vy, vz, vt):
            """Oblique isometric 4D→2D with T as depth shift."""
            angle = math.radians(30)
            px = vx * 20 + vy * 8 + vz * math.cos(angle) * 6 + vt * 3
            py = vy * 6  - vz * math.sin(angle) * 4 - vt * 2
            return int(px) + 2, int(py) + 4

        # Draw edges (vertices that differ in exactly one dimension)
        edges = [
            (v1, v2) for i, v1 in enumerate(vertices_4d)
            for v2 in vertices_4d[i+1:]
            if sum(a != b for a, b in zip(v1, v2)) == 1
        ]

        chars_by_t = {0: "·", 1: "○"}  # T=0 dim, T=1 bright

        for (x1,y1,z1,t1), (x2,y2,z2,t2) in edges:
            px1, py1 = project(x1,y1,z1,t1)
            px2, py2 = project(x2,y2,z2,t2)
            steps = max(abs(px2-px1), abs(py2-py1), 1)
            for s in range(steps+1):
                fx = px1 + int((px2-px1) * s / steps)
                fy = py1 + int((py2-py1) * s / steps)
                if 0 <= fy < grid_h and 0 <= fx < grid_w:
                    # T-dimension pulsation
                    avg_t = (t1 + t2) / 2
                    pulsed = math.sin(tick * 2 + avg_t * math.pi) > 0
                    canvas[fy][fx] = "◈" if pulsed else "·"

        # Render with colors
        for row_i, row in enumerate(canvas):
            line = "  "
            for col_i, ch in enumerate(row):
                if ch != " ":
                    intensity = (col_i / grid_w + row_i / grid_h) / 2
                    r = int(50 + intensity * 100)
                    g = int(100 + intensity * 155)
                    b = int(200 + (1-intensity) * 55)
                    line += fg(r, g, b) + ch + RESET
                else:
                    line += ch
            print(line)

    # ── 5. Temporal waveform ─────────────────────────────────────────────
    def temporal_waveform(self, ticks: int = 40) -> None:
        """Show ethical load wave over simulated time."""
        print(f"\n{BOLD}{fg(255,180,80)}  〜 TEMPORAL ETHICAL WAVEFORM  (Σ Z over T){RESET}")
        height = 8

        # Build wave from all world-lines
        wave = []
        for tick in range(ticks):
            t_norm = tick / ticks
            # Superposition of ethical weights at this tick
            total = sum(
                ETHICAL_WEIGHT.get(state, 0.5) * math.exp(-abs(t_norm - (idx / 10)))
                for idx, state in enumerate(ETHICAL_WEIGHT.keys())
            ) / len(ETHICAL_WEIGHT)
            wave.append(min(1.0, total))

        max_wave = max(wave) or 1.0

        for row in range(height, 0, -1):
            threshold = row / height
            line = "  "
            for val in wave:
                normalized = val / max_wave
                if normalized >= threshold:
                    col = ethical_color(val)
                    line += col + "▓" + RESET
                else:
                    line += DIM + "░" + RESET
            print(line)
        print("  " + fg(100,100,100) + "─" * ticks + RESET)
        print("  " + fg(100,100,100) + "T=0" + " " * (ticks - 6) + f"T={ticks}" + RESET)

    # ── 6. Manifold summary ───────────────────────────────────────────────
    def manifold_summary(self) -> None:
        """Print scientific summary panel."""
        s = self.st.manifold_summary()
        print(f"\n{BOLD}{fg(160,255,200)}  ∑ MANIFOLD SUMMARY{RESET}")
        for k, v in s.items():
            print(f"  {fg(180,180,255)}{k:<30}{RESET} {fg(255,255,100)}{v}{RESET}")

    # ── Full render ───────────────────────────────────────────────────────
    def render(self, tick: float = 0.0) -> None:
        """Full 4D immersive render pass."""
        self.banner()
        self.ethical_heatmap()
        self.hypercube(tick=tick)
        self.temporal_waveform()
        self.world_lines()
        self.manifold_summary()
