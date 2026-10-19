"""Force / free-body diagram renderer.

The solver decides *which* forces exist and *in which direction*; this module
only draws them faithfully. Angles are absolute: 0 deg = +x (right), 90 deg =
up. Nothing here infers a force direction from the picture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from .canvas import PALETTE, Canvas, RenderError, Style, combined_bbox

__all__ = ["render_force", "ForceStats"]

Point = tuple[float, float]

INK = Style(stroke=PALETTE["ink"], width=2.0)
FORCE = Style(stroke=PALETTE["accent"], width=2.4)
GRAVITY = Style(stroke=PALETTE["accent2"], width=2.4)
DASHED = Style(stroke=PALETTE["aux"], width=1.2, dash="5 5")
OBJECT_FILL = "#f3f4f6"

INCLINE_BASE_Y = -1.0
INCLINE_HALF_WIDTH = 3.2


@dataclass
class ForceStats:
    forces: int = 0
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    warnings: list[str] = field(default_factory=list)


def _angle_vector(angle_deg: float) -> Point:
    radians = math.radians(float(angle_deg))
    return (math.cos(radians), math.sin(radians))


def _incline_origin(angle_deg: float) -> Point:
    slope = math.tan(math.radians(angle_deg))
    return (0.0, INCLINE_BASE_Y + INCLINE_HALF_WIDTH * slope)


def render_force(spec: Mapping[str, Any], canvas: Canvas) -> ForceStats:
    stats = ForceStats()
    forces = list(spec.get("forces") or [])
    if not forces:
        raise RenderError("empty_forces", "force diagram needs at least one force")

    object_spec = spec.get("object") or {}
    incline_angle = spec.get("incline_angle")
    shape = object_spec.get("shape") or ("incline" if incline_angle else "block")
    if shape == "incline" and not incline_angle:
        raise RenderError("invalid_incline", "object shape 'incline' needs incline_angle")

    origin: Point = _incline_origin(float(incline_angle)) if shape == "incline" else (0.0, 0.0)
    # Forces act on the object's centre. On an incline the centre sits one
    # half-block above the slope surface.
    if shape == "incline":
        angle = math.radians(float(incline_angle))
        origin = (origin[0] - math.sin(angle) * 0.45, origin[1] + math.cos(angle) * 0.45)

    magnitudes = [float(item["magnitude"]) for item in forces if item.get("magnitude")]
    magnitude_max = max(magnitudes) if magnitudes else None
    lengths = [
        1.5 + 2.0 * math.sqrt(float(item["magnitude"]) / magnitude_max)
        if magnitude_max and item.get("magnitude")
        else 2.4
        for item in forces
    ]

    extents: list[Point] = [origin, (-3.6, -1.2), (3.6, 2.2)]
    for item, length in zip(forces, lengths):
        ux, uy = _angle_vector(float(item["angle_deg"]))
        extents.append((origin[0] + ux * (0.7 + length), origin[1] + uy * (0.7 + length)))
    for key in ("velocity", "acceleration"):
        entry = spec.get(key)
        if entry:
            ux, uy = _angle_vector(float(entry.get("angle_deg") or 0))
            extents.append((origin[0] + 1.5 + ux * 2.6, origin[1] - 1.0 + uy * 2.6))
            extents.append((origin[0] + 1.5, origin[1] - 1.0))
    bbox = combined_bbox(extents)
    canvas.fit(combined_bbox(extents, pad=0.4), margin=76, uniform=True)
    stats.bbox = bbox

    # ---- surface / object
    if shape == "incline":
        angle = math.radians(float(incline_angle))
        base_left: Point = (-INCLINE_HALF_WIDTH, INCLINE_BASE_Y)
        base_right: Point = (INCLINE_HALF_WIDTH, INCLINE_BASE_Y)
        apex: Point = (INCLINE_HALF_WIDTH, INCLINE_BASE_Y + 2 * INCLINE_HALF_WIDTH * math.tan(angle))
        canvas.polygon([base_left, base_right, apex], Style(fill="#f9fafb", stroke=PALETTE["muted"], width=1.6))
        canvas.arc(base_right, 1.2, 180 - float(incline_angle), 180, Style(stroke=PALETTE["muted"], width=1.2))
        canvas.text((base_right[0] - 1.45, base_right[1] + 0.22), f"{float(incline_angle):g}°", size=12, color=PALETTE["muted"])
        ux, uy = math.cos(angle), math.sin(angle)
        nx, ny = -math.sin(angle), math.cos(angle)
        half = 0.42
        center = origin
        corners = [
            (center[0] + ux * half + nx * half, center[1] + uy * half + ny * half),
            (center[0] - ux * half + nx * half, center[1] - uy * half + ny * half),
            (center[0] - ux * half - nx * half, center[1] - uy * half - ny * half),
            (center[0] + ux * half - nx * half, center[1] + uy * half - ny * half),
        ]
        canvas.polygon(corners, Style(fill=OBJECT_FILL, stroke=PALETTE["ink"], width=1.8))
    elif shape == "block":
        half_w, half_h = 1.1, 0.65
        canvas.polygon(
            [
                (origin[0] - half_w, origin[1] - half_h),
                (origin[0] + half_w, origin[1] - half_h),
                (origin[0] + half_w, origin[1] + half_h),
                (origin[0] - half_w, origin[1] + half_h),
            ],
            Style(fill=OBJECT_FILL, stroke=PALETTE["ink"], width=1.9),
        )
    else:
        canvas.dot(origin, 6.0, PALETTE["ink"])
        canvas.circle(origin, canvas.screen_length(9.0), Style(stroke=PALETTE["ink"], width=1.0))

    if object_spec.get("label"):
        canvas.text(origin, str(object_spec["label"]), size=15, anchor="middle", baseline="middle", bold=True)

    if spec.get("axes"):
        # A small coordinate triad in the corner: drawing axes through the
        # object would overlap the force arrows.
        base = (86.0, canvas.height - 86.0)
        canvas.arrow_screen(base, (base[0] + 54.0, base[1]), DASHED, head=8.0)
        canvas.arrow_screen(base, (base[0], base[1] - 54.0), DASHED, head=8.0)
        canvas.text_screen((base[0] + 66.0, base[1]), "x", size=12, color=PALETTE["aux"])
        canvas.text_screen((base[0], base[1] - 66.0), "y", size=12, color=PALETTE["aux"])

    # ---- forces
    for item, length in zip(forces, lengths):
        ux, uy = _angle_vector(float(item["angle_deg"]))
        if shape == "incline":
            surface = 0.62
        elif shape == "block":
            surface = 1.0 / math.sqrt((ux / 1.1) ** 2 + (uy / 0.65) ** 2)
        else:
            surface = 0.3
        start = (origin[0] + ux * surface, origin[1] + uy * surface)
        end = (origin[0] + ux * (surface + length), origin[1] + uy * (surface + length))
        label = str(item.get("label") or "")
        if item.get("magnitude") and item.get("unit"):
            label = f"{label} = {item['magnitude']:g} {item['unit']}"
        style = GRAVITY if label.startswith("mg") else FORCE
        if item.get("style") == "dashed":
            style = Style(stroke=style.stroke, width=style.width, dash="7 5")
        canvas.arrow(start, end, style, head=11.0, color=style.stroke)
        if label:
            canvas.text(
                end,
                label,
                size=14,
                color=style.stroke,
                anchor="middle",
                offset=(ux * 26, -uy * 26 - 4),
                background="#ffffff",
            )
        stats.forces += 1

    # ---- kinematics vectors (drawn from a separate anchor so they never
    # overlap the force arrows)
    kinematics = [
        (key, color, default_label, entry)
        for key, color, default_label in (
            ("velocity", PALETTE["green"], "v"),
            ("acceleration", PALETTE["highlight"], "a"),
        )
        for entry in [spec.get(key)]
        if entry
    ]
    for index, (key, color, default_label, entry) in enumerate(kinematics):
        anchor = (origin[0] + 1.5, origin[1] - 1.0 - index * 0.75)
        ux, uy = _angle_vector(float(entry.get("angle_deg") or 0))
        canvas.dot(anchor, 2.2, PALETTE["aux"])
        canvas.arrow(
            (anchor[0] + ux * 0.2, anchor[1] + uy * 0.2),
            (anchor[0] + ux * 2.4, anchor[1] + uy * 2.4),
            Style(stroke=color, width=1.8, dash="6 4"),
            label=str(entry.get("label") or default_label),
            label_offset=(ux * 10, -uy * 10 - 12),
            color=color,
        )

    if spec.get("coordinate_note"):
        canvas.text_screen(
            (24, canvas.height - 22), str(spec["coordinate_note"]), size=12, anchor="start", color=PALETTE["muted"]
        )
    if spec.get("title"):
        canvas.text_screen((24, 26), str(spec["title"]), size=16, anchor="start", baseline="middle", bold=True)
    return stats
