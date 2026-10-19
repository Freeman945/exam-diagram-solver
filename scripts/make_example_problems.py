#!/usr/bin/env python
"""Generate the self-authored example problem images under ``examples/problems``.

These are synthetic exam-style pages written for this repository, so they can
be committed without any third-party copyright concerns. Run with any Python
that has matplotlib:

    python scripts/make_example_problems.py
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Polygon

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples" / "problems"

FONT = "Microsoft YaHei"
plt.rcParams["font.sans-serif"] = [FONT, "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

PAGE = (1200, 800)


def page(title: str | None = None):
    fig = plt.figure(figsize=(PAGE[0] / 200, PAGE[1] / 200), dpi=200)
    fig.patch.set_facecolor("#fdfdfb")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    ax.add_patch(
        plt.Rectangle((0.02, 0.02), 0.96, 0.96, fill=False, edgecolor="#d8d8d0", linewidth=1.2)
    )
    if title:
        ax.text(0.05, 0.94, title, fontsize=11, color="#7a7a72")
    return fig, ax


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


def math_quadratic() -> None:
    fig, ax = page("数学 · 一元二次方程")
    ax.text(0.06, 0.84, r"1. 解方程：$x^2-5x+6=0$", fontsize=18, color="#1f2937")
    ax.text(0.06, 0.74, r"2. 若 $x_1$、$x_2$ 是该方程的两个根，", fontsize=18, color="#1f2937")
    ax.text(0.055, 0.655, r"求 $x_1^2+x_2^2$ 的值。", fontsize=18, color="#1f2937")
    ax.text(0.06, 0.55, "（要求写出完整过程）", fontsize=13, color="#6b7280")
    save(fig, "math_quadratic.png")


def geometry_proof() -> None:
    fig, ax = page("数学 · 平面几何证明")
    ax.text(0.06, 0.895, "如图，在 △ABC 中，AB = AC，D 是 BC 的中点。", fontsize=17, color="#1f2937")
    ax.text(0.06, 0.835, "求证：AD ⊥ BC。", fontsize=17, color="#1f2937")

    # Figure coordinates in figure space (0..1).
    A = (0.50, 0.62)
    B = (0.30, 0.28)
    C = (0.70, 0.28)
    D = (0.50, 0.28)
    ax.plot([A[0], B[0]], [A[1], B[1]], color="#111827", linewidth=2)
    ax.plot([A[0], C[0]], [A[1], C[1]], color="#111827", linewidth=2)
    ax.plot([B[0], C[0]], [B[1], C[1]], color="#111827", linewidth=2)
    ax.plot([A[0], D[0]], [A[1], D[1]], color="#111827", linewidth=2)

    for point in (A, B, C, D):
        ax.plot(point[0], point[1], "o", color="#111827", markersize=4)
    ax.text(A[0], A[1] + 0.035, "A", fontsize=17, ha="center")
    ax.text(B[0] - 0.035, B[1] - 0.01, "B", fontsize=17, ha="center")
    ax.text(C[0] + 0.035, C[1] - 0.01, "C", fontsize=17, ha="center")
    ax.text(D[0], D[1] - 0.06, "D", fontsize=17, ha="center")

    # Equal-length ticks on AB and AC.
    def tick(p, q):
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = math.hypot(dx, dy)
        nx, ny = -dy / length, dx / length
        ax.plot([mx + nx * 0.012, mx - nx * 0.012], [my + ny * 0.012, my - ny * 0.012],
                color="#b91c1c", linewidth=2)

    tick(A, B)
    tick(A, C)

    save(fig, "geometry_proof.png")


def physics_force() -> None:
    fig, ax = page("物理 · 牛顿运动定律")
    lines = [
        "质量 m = 2 kg 的物块静止在粗糙水平面上，",
        "受到水平向右的拉力 F = 10 N，动摩擦因数 μ = 0.2，",
        "g 取 10 m/s²。求物块运动的加速度。",
    ]
    y = 0.83
    for line in lines:
        ax.text(0.06, y, line, fontsize=16, color="#1f2937")
        y -= 0.07

    # Simple illustration of the block on a surface.
    ax.add_patch(plt.Rectangle((0.30, 0.34), 0.16, 0.10, facecolor="#e5e7eb", edgecolor="#111827", linewidth=1.6))
    ax.plot([0.22, 0.78], [0.34, 0.34], color="#111827", linewidth=2)
    for x in [0.24, 0.32, 0.40, 0.48, 0.56, 0.64, 0.72, 0.78]:
        ax.plot([x, x - 0.02], [0.34, 0.315], color="#9ca3af", linewidth=1)
    ax.add_patch(
        FancyArrowPatch((0.46, 0.39), (0.66, 0.39), arrowstyle="-|>", mutation_scale=18, color="#1d4ed8", linewidth=2)
    )
    ax.text(0.66, 0.40, "F", fontsize=15, color="#1d4ed8")
    ax.text(0.38, 0.455, "m", fontsize=15, color="#111827")
    save(fig, "physics_force.png")


def main() -> None:
    math_quadratic()
    geometry_proof()
    physics_force()


if __name__ == "__main__":
    main()
