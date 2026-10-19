"""Resolution-independent drawing canvas with SVG and raster backends.

Renderers never manipulate an output format directly: they compute geometry in
*diagram coordinates* and call high-level primitives (:meth:`Canvas.line`,
:meth:`Canvas.text`, ...). Two backends then produce identical output:

``SVGCanvas``
    Pure-Python, dependency-free, deterministic and diff-friendly. This is the
    canonical output of the project.

``MplCanvas``
    Matplotlib Agg raster backend used only for the inline PNG preview in the
    chat UI. Imported lazily so the engine still works without matplotlib.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

__all__ = ["Canvas", "SVGCanvas", "MplCanvas", "Style", "RenderError", "PALETTE", "FONT"]

Point = tuple[float, float]

FONT = "Segoe UI, Microsoft YaHei, PingFang SC, sans-serif"

PALETTE = {
    "ink": "#1f2937",
    "muted": "#6b7280",
    "accent": "#1d4ed8",
    "accent2": "#b91c1c",
    "fill": "#dbeafe",
    "fill_soft": "#eff6ff",
    "grid": "#e5e7eb",
    "aux": "#9ca3af",
    "highlight": "#c2410c",
    "green": "#15803d",
}


class RenderError(RuntimeError):
    """Raised when a diagram cannot be drawn as specified."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Style:
    """Stroke/fill description shared by every primitive."""

    stroke: str = PALETTE["ink"]
    width: float = 1.8
    dash: str | None = None  # SVG stroke-dasharray, e.g. "6 4"
    fill: str = "none"
    opacity: float = 1.0
    cap: str = "round"


class Canvas:
    """Base canvas: world -> screen transform plus composed primitives."""

    def __init__(self, width: int = 760, height: int = 560) -> None:
        self.width = int(width)
        self.height = int(height)
        self.sx = 1.0
        self.sy = 1.0
        self.ox = 0.0
        self.oy = 0.0
        self._background = "#ffffff"

    # ------------------------------------------------------------------ view
    def set_view(self, sx: float, sy: float, ox: float, oy: float) -> None:
        """Set the affine mapping ``screen = (ox + x*sx, oy - y*sy)``."""

        if not all(math.isfinite(value) for value in (sx, sy, ox, oy)) or sx == 0 or sy == 0:
            raise RenderError("invalid_view", "non-finite or degenerate view transform")
        self.sx, self.sy, self.ox, self.oy = sx, sy, ox, oy

    def fit(
        self,
        bbox: tuple[float, float, float, float],
        *,
        margin: float = 56.0,
        uniform: bool = True,
        max_scale: float | None = None,
    ) -> None:
        """Fit a world-space bounding box into the canvas with a pixel margin."""

        x0, y0, x1, y1 = bbox
        if not all(math.isfinite(value) for value in bbox):
            raise RenderError("invalid_bbox", "bounding box contains non-finite values")
        span_x = max(x1 - x0, 1e-9)
        span_y = max(y1 - y0, 1e-9)
        usable_w = max(self.width - 2 * margin, 40.0)
        usable_h = max(self.height - 2 * margin, 40.0)
        sx = usable_w / span_x
        sy = usable_h / span_y
        if uniform:
            sx = sy = min(sx, sy)
        if max_scale is not None:
            sx = min(sx, max_scale)
            sy = min(sy, max_scale)
        ox = (self.width - span_x * sx) / 2 - x0 * sx
        oy = self.height / 2 + sy * (y0 + y1) / 2
        self.set_view(sx, sy, ox, oy)

    def to_screen(self, point: Point) -> Point:
        return (self.ox + point[0] * self.sx, self.oy - point[1] * self.sy)

    def scale(self) -> float:
        return min(abs(self.sx), abs(self.sy))

    # ------------------------------------------------------------ primitives
    def line(self, a: Point, b: Point, style: Style | None = None) -> None:
        style = style or Style()
        self._segment(self.to_screen(a), self.to_screen(b), style)

    def polyline(self, points: Sequence[Point], style: Style | None = None) -> None:
        if len(points) < 2:
            return
        style = style or Style()
        self._polyline([self.to_screen(point) for point in points], style, closed=False)

    def polygon(self, points: Sequence[Point], style: Style | None = None) -> None:
        if len(points) < 3:
            return
        style = style or Style()
        self._polyline([self.to_screen(point) for point in points], style, closed=True)

    def circle(self, center: Point, radius: float, style: Style | None = None) -> None:
        style = style or Style()
        if radius <= 0:
            raise RenderError("invalid_radius", f"circle radius must be positive, got {radius}")
        cx, cy = self.to_screen(center)
        self._circle((cx, cy), radius * abs(self.sx), style)

    def dot(self, center: Point, radius: float = 3.6, color: str = PALETTE["ink"]) -> None:
        cx, cy = self.to_screen(center)
        self._circle((cx, cy), radius, Style(fill=color, stroke=color, width=0.8))

    def arc(
        self,
        center: Point,
        radius: float,
        start_deg: float,
        end_deg: float,
        style: Style | None = None,
        *,
        samples: int = 72,
    ) -> None:
        """Draw a circular arc from ``start_deg`` to ``end_deg`` (CCW, degrees)."""

        if radius <= 0:
            raise RenderError("invalid_radius", "arc radius must be positive")
        sweep = end_deg - start_deg
        if abs(sweep) > 360:
            sweep = 360 if sweep > 0 else -360
        count = max(8, int(samples * abs(sweep) / 360))
        points = [
            (
                center[0] + radius * math.cos(math.radians(start_deg + sweep * index / count)),
                center[1] + radius * math.sin(math.radians(start_deg + sweep * index / count)),
            )
            for index in range(count + 1)
        ]
        self.polyline(points, style)

    def arrow(
        self,
        a: Point,
        b: Point,
        style: Style | None = None,
        *,
        head: float = 11.0,
        label: str | None = None,
        label_offset: tuple[float, float] = (0.0, -12.0),
        label_size: float = 15.0,
        color: str | None = None,
    ) -> None:
        """Straight arrow from ``a`` to ``b`` with a screen-space head."""

        style = style or Style()
        (x0, y0), (x1, y1) = self.to_screen(a), self.to_screen(b)
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 0.5:
            return
        ux, uy = dx / length, dy / length
        # Shorten the shaft so it does not poke through the head.
        shaft_end = (x1 - ux * head * 0.85, y1 - uy * head * 0.85)
        self._segment((x0, y0), shaft_end, style)
        # Head in screen space, built as a filled triangle.
        px, py = -uy, ux
        base = (x1 - ux * head, y1 - uy * head)
        half = head * 0.42
        head_points = [
            (x1, y1),
            (base[0] + px * half, base[1] + py * half),
            (base[0] - px * half, base[1] - py * half),
        ]
        self._polyline(head_points, Style(fill=color or style.stroke, stroke=color or style.stroke, width=1.0), closed=True)
        if label:
            mid = ((x0 + x1) / 2 + label_offset[0], (y0 + y1) / 2 + label_offset[1])
            self._text(mid, label, size=label_size, anchor="middle", baseline="middle", color=color or style.stroke)

    def text(
        self,
        at: Point,
        text: str,
        *,
        size: float = 16.0,
        anchor: str = "middle",
        baseline: str = "middle",
        color: str = PALETTE["ink"],
        rotation: float = 0.0,
        bold: bool = False,
        italic: bool = False,
        background: str | None = None,
        offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        screen = self.to_screen(at)
        self.text_screen(
            (screen[0] + offset[0], screen[1] + offset[1]),
            text,
            size=size,
            anchor=anchor,
            baseline=baseline,
            color=color,
            rotation=rotation,
            bold=bold,
            italic=italic,
            background=background,
        )

    def text_screen(
        self,
        at: Point,
        text: str,
        *,
        size: float = 16.0,
        anchor: str = "middle",
        baseline: str = "middle",
        color: str = PALETTE["ink"],
        rotation: float = 0.0,
        bold: bool = False,
        italic: bool = False,
        background: str | None = None,
    ) -> None:
        """Draw text at an already-projected screen position."""

        self._text(
            at,
            text,
            size=size,
            anchor=anchor,
            baseline=baseline,
            color=color,
            rotation=rotation,
            bold=bold,
            italic=italic,
            background=background,
        )

    # ---------------------------------------------------- screen-space helpers
    def line_screen(self, a: Point, b: Point, style: Style | None = None) -> None:
        """Draw a line whose endpoints are already in screen pixels."""

        self._segment(a, b, style or Style())

    def polyline_screen(self, points: Sequence[Point], style: Style | None = None, *, closed: bool = False) -> None:
        if len(points) < 2:
            return
        self._polyline(points, style or Style(), closed=closed)

    def circle_screen(self, center: Point, radius: float, style: Style | None = None) -> None:
        self._circle(center, radius, style or Style())

    def dot_screen(self, center: Point, radius: float = 3.6, color: str = PALETTE["ink"]) -> None:
        self._circle(center, radius, Style(fill=color, stroke=color, width=0.8))

    def screen_length(self, pixels: float) -> float:
        """Convert a pixel length into world units for the current view."""

        return pixels / max(self.scale(), 1e-6)

    def arrow_screen(
        self,
        a: Point,
        b: Point,
        style: Style,
        *,
        head: float = 10.0,
        label: str | None = None,
        label_offset: tuple[float, float] = (0.0, -12.0),
        label_size: float = 14.0,
    ) -> None:
        """Arrow between two screen points (used by schematic symbols)."""

        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 0.5:
            return
        ux, uy = dx / length, dy / length
        self._segment(a, (b[0] - ux * head * 0.85, b[1] - uy * head * 0.85), style)
        px, py = -uy, ux
        base = (b[0] - ux * head, b[1] - uy * head)
        half = head * 0.42
        self._polyline(
            [(b[0], b[1]), (base[0] + px * half, base[1] + py * half), (base[0] - px * half, base[1] - py * half)],
            Style(fill=style.stroke, stroke=style.stroke, width=1.0),
            closed=True,
        )
        if label:
            self._text(
                ((a[0] + b[0]) / 2 + label_offset[0], (a[1] + b[1]) / 2 + label_offset[1]),
                label,
                size=label_size,
                anchor="middle",
                baseline="middle",
                color=style.stroke,
            )

    # ---------------------------------------------------------- primitives (backend)
    def _segment(self, a: Point, b: Point, style: Style) -> None:  # pragma: no cover
        raise NotImplementedError

    def _polyline(self, points: Sequence[Point], style: Style, *, closed: bool) -> None:  # pragma: no cover
        raise NotImplementedError

    def _circle(self, center: Point, radius: float, style: Style) -> None:  # pragma: no cover
        raise NotImplementedError

    def _text(
        self,
        at: Point,
        text: str,
        *,
        size: float,
        anchor: str,
        baseline: str,
        color: str,
        rotation: float = 0.0,
        bold: bool = False,
        italic: bool = False,
        background: str | None = None,
    ) -> None:  # pragma: no cover
        raise NotImplementedError

    # --------------------------------------------------------------- output
    def save_svg(self, path: str | Path, *, title: str | None = None) -> Path:
        raise NotImplementedError

    def save_png(self, path: str | Path, *, dpi: int = 150) -> Path:
        raise NotImplementedError


# --------------------------------------------------------------------------- SVG


class SVGCanvas(Canvas):
    """Deterministic SVG writer."""

    def __init__(self, width: int = 760, height: int = 560) -> None:
        super().__init__(width, height)
        self._parts: list[str] = []

    # -- helpers
    @staticmethod
    def _fmt(value: float) -> str:
        if abs(value) < 1e-9:
            value = 0.0
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return text or "0"

    def _paint(self, style: Style) -> str:
        parts = [
            f'stroke="{style.stroke}"',
            f'stroke-width="{self._fmt(style.width)}"',
            f'fill="{style.fill}"',
            'stroke-linejoin="round"',
            f'stroke-linecap="{style.cap}"',
        ]
        if style.dash:
            parts.append(f'stroke-dasharray="{style.dash}"')
        if style.opacity < 1.0:
            parts.append(f'opacity="{style.opacity:.2f}"')
        return " ".join(parts)

    def _segment(self, a: Point, b: Point, style: Style) -> None:
        self._parts.append(
            f'<line x1="{self._fmt(a[0])}" y1="{self._fmt(a[1])}" '
            f'x2="{self._fmt(b[0])}" y2="{self._fmt(b[1])}" {self._paint(style)}/>'
        )

    def _polyline(self, points: Sequence[Point], style: Style, *, closed: bool) -> None:
        if not points:
            return
        head = "polygon" if closed else "polyline"
        joined = " ".join(f"{self._fmt(x)},{self._fmt(y)}" for x, y in points)
        self._parts.append(f'<{head} points="{joined}" {self._paint(style)}/>')

    def _circle(self, center: Point, radius: float, style: Style) -> None:
        self._parts.append(
            f'<circle cx="{self._fmt(center[0])}" cy="{self._fmt(center[1])}" '
            f'r="{self._fmt(max(radius, 0.2))}" {self._paint(style)}/>'
        )

    def _text(
        self,
        at: Point,
        text: str,
        *,
        size: float,
        anchor: str,
        baseline: str,
        color: str,
        rotation: float = 0.0,
        bold: bool = False,
        italic: bool = False,
        background: str | None = None,
    ) -> None:
        if not text:
            return
        weight = ' font-weight="600"' if bold else ""
        style_attr = ' font-style="italic"' if italic else ""
        transform = (
            f' transform="rotate({self._fmt(-rotation)} {self._fmt(at[0])} {self._fmt(at[1])})"'
            if abs(rotation) > 1e-6
            else ""
        )
        if background:
            width = max(len(text), 1) * size * 0.62
            self._parts.append(
                f'<rect x="{self._fmt(at[0] - width / 2)}" y="{self._fmt(at[1] - size * 0.72)}" '
                f'width="{self._fmt(width)}" height="{self._fmt(size * 1.3)}" rx="3" fill="{background}" opacity="0.85"/>'
            )
        self._parts.append(
            f'<text x="{self._fmt(at[0])}" y="{self._fmt(at[1])}" font-family="{FONT}" '
            f'font-size="{self._fmt(size)}" fill="{color}" text-anchor="{anchor}" '
            f'dominant-baseline="{baseline}"{weight}{style_attr}{transform}>{escape(text)}</text>'
        )

    def save_svg(self, path: str | Path, *, title: str | None = None) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        header = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">',
            f"<title>{escape(title or 'diagram')}</title>",
            f'<rect width="{self.width}" height="{self.height}" fill="{self._background}"/>',
        ]
        footer = ["</svg>"]
        target.write_text("\n".join(header + self._parts + footer), encoding="utf-8")
        return target


# ------------------------------------------------------------------------- PNG


class MplCanvas(Canvas):
    """Matplotlib Agg backend. Requires :mod:`matplotlib` at use time only."""

    def __init__(self, width: int = 760, height: int = 560, *, dpi: int = 150) -> None:
        super().__init__(width, height)
        try:
            import matplotlib

            matplotlib.use("Agg", force=True)
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RenderError("matplotlib_unavailable", f"matplotlib is required for PNG output: {exc}") from exc
        matplotlib.rcParams["font.sans-serif"] = [
            "Microsoft YaHei",
            "SimHei",
            "Noto Sans CJK SC",
            "PingFang SC",
            "DejaVu Sans",
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False
        self._dpi = dpi
        self._figure = Figure(figsize=(width / dpi, height / dpi), dpi=dpi)
        self._figure.patch.set_facecolor("#ffffff")
        FigureCanvasAgg(self._figure)
        self._axes = self._figure.add_axes((0, 0, 1, 1))
        self._axes.set_xlim(0, width)
        self._axes.set_ylim(height, 0)
        self._axes.set_axis_off()
        self._axes.set_facecolor("#ffffff")

    def _segment(self, a: Point, b: Point, style: Style) -> None:
        line, = self._axes.plot(
            [a[0], b[0]],
            [a[1], b[1]],
            color=style.stroke,
            linewidth=max(style.width * 0.72, 0.4),
            solid_capstyle="round",
            alpha=style.opacity,
            zorder=3,
        )
        if style.dash:
            line.set_dashes(_dash_pattern(style.dash))

    def _polyline(self, points: Sequence[Point], style: Style, *, closed: bool) -> None:
        if not points:
            return
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        if closed:
            from matplotlib.patches import Polygon

            # Filled shapes sit *below* strokes so interior lines stay visible;
            # this keeps the PNG identical to the SVG draw order.
            filled = style.fill != "none"
            patch = Polygon(
                list(zip(xs, ys)),
                closed=True,
                facecolor="none" if style.fill == "none" else style.fill,
                edgecolor=style.stroke,
                linewidth=max(style.width * 0.72, 0.4),
                alpha=style.opacity,
                zorder=1 if filled else 3,
            )
            if style.dash:
                patch.set_linestyle((0, tuple(_dash_pattern(style.dash))))
            self._axes.add_patch(patch)
        else:
            line, = self._axes.plot(
                xs,
                ys,
                color=style.stroke,
                linewidth=max(style.width * 0.72, 0.4),
                solid_capstyle="round",
                alpha=style.opacity,
                zorder=3,
            )
            if style.dash:
                line.set_dashes(_dash_pattern(style.dash))

    def _circle(self, center: Point, radius: float, style: Style) -> None:
        from matplotlib.patches import Circle

        filled = style.fill != "none"
        patch = Circle(
            center,
            radius,
            facecolor="none" if style.fill == "none" else style.fill,
            edgecolor=style.stroke,
            linewidth=max(style.width * 0.72, 0.4),
            alpha=style.opacity,
            zorder=1 if filled else 3,
        )
        if style.dash:
            patch.set_linestyle((0, tuple(_dash_pattern(style.dash))))
        self._axes.add_patch(patch)

    def _text(
        self,
        at: Point,
        text: str,
        *,
        size: float,
        anchor: str,
        baseline: str,
        color: str,
        rotation: float = 0.0,
        bold: bool = False,
        italic: bool = False,
        background: str | None = None,
    ) -> None:
        if not text:
            return
        horizontal = {"start": "left", "middle": "center", "end": "right"}.get(anchor, "center")
        vertical = {"middle": "center", "hanging": "top", "alphabetic": "baseline"}.get(baseline, "center")
        bbox = None
        if background:
            bbox = {"facecolor": background, "edgecolor": "none", "alpha": 0.85, "pad": 1.2}
        self._axes.text(
            at[0],
            at[1],
            text,
            ha=horizontal,
            va=vertical,
            fontsize=size * 0.75,
            color=color,
            rotation=rotation,
            fontweight="bold" if bold else "normal",
            fontstyle="italic" if italic else "normal",
            bbox=bbox,
            zorder=5,
            clip_on=False,
        )

    def save_png(self, path: str | Path, *, dpi: int | None = None) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._figure.savefig(target, dpi=dpi or self._dpi, facecolor="#ffffff")
        return target


def _dash_pattern(spec: str) -> list[float]:
    values = []
    for chunk in spec.replace(",", " ").split():
        try:
            values.append(max(float(chunk), 0.5))
        except ValueError:
            continue
    return values or [6.0, 4.0]


def combined_bbox(points: Iterable[Point], pad: float = 0.0) -> tuple[float, float, float, float]:
    """Axis-aligned bounding box of the given points."""

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    if not xs:
        return (-1.0 + pad, -1.0 + pad, 1.0 - pad, 1.0 - pad)
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def style_with(style: Style, **changes: object) -> Style:
    """Small helper for immutable style tweaks."""

    return replace(style, **changes)  # type: ignore[arg-type]
