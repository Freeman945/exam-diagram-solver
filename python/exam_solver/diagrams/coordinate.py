"""Function and coordinate renderer backed by SymPy analysis.

The model never "sketches" a curve: it supplies an expression and the renderer
derives sampling, key points, and a sane viewport from symbolic analysis.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .canvas import PALETTE, Canvas, RenderError, Style

__all__ = [
    "analyze_expression",
    "render_coordinate",
    "render_chart",
    "FunctionAnalysis",
    "CoordinateStats",
]

Point = tuple[float, float]

CURVE = Style(stroke=PALETTE["accent"], width=2.4)
CURVE2 = Style(stroke=PALETTE["highlight"], width=2.0, dash="7 4")
AXIS = Style(stroke=PALETTE["ink"], width=1.6)
GRID = Style(stroke=PALETTE["grid"], width=1.0)
GUIDE = Style(stroke=PALETTE["aux"], width=1.2, dash="5 5")


@dataclass
class FunctionAnalysis:
    """Symbolic facts about one real function of one variable."""

    expression: str
    variable: str = "x"
    roots: list[float] = field(default_factory=list)
    y_intercept: float | None = None
    extrema: list[tuple[float, float]] = field(default_factory=list)
    vertical_asymptotes: list[float] = field(default_factory=list)
    symmetric_about_y_axis: bool = False
    simplified: str = ""
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "variable": self.variable,
            "simplified": self.simplified,
            "roots": _round_list(self.roots),
            "y_intercept": None if self.y_intercept is None else _round(self.y_intercept),
            "extrema": [{"x": _round(x), "y": _round(y)} for x, y in self.extrema],
            "vertical_asymptotes": _round_list(self.vertical_asymptotes),
            "symmetric_about_y_axis": self.symmetric_about_y_axis,
            "error": self.error,
        }


def _round(value: float, digits: int = 4) -> float:
    if value is None or not math.isfinite(value):
        return 0.0
    return round(float(value), digits)


def _round_list(values: Sequence[float]) -> list[float]:
    return [_round(value) for value in values]


def _sympy():  # imported lazily so geometry rendering works without SymPy
    try:
        import sympy as sp

        return sp
    except Exception as exc:  # pragma: no cover - environment failure
        raise RenderError("sympy_unavailable", f"SymPy is required for function analysis: {exc}") from exc


def analyze_expression(expression: str, variable: str = "x") -> FunctionAnalysis:
    """Parse ``expression`` and extract roots, extrema and asymptotes.

    Non-real or non-numeric solutions are dropped instead of being guessed.
    Any SymPy failure is reported in :attr:`FunctionAnalysis.error` and the
    caller decides whether to continue with a numeric-only plot.
    """

    sp = _sympy()
    result = FunctionAnalysis(expression=expression, variable=variable)
    try:
        symbol = sp.Symbol(variable, real=True)
        local = {variable: symbol}
        local.update({"sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "sqrt": sp.sqrt, "exp": sp.exp,
                      "log": sp.log, "ln": sp.log, "abs": sp.Abs, "pi": sp.pi, "e": sp.E})
        expr = sp.sympify(expression.replace("^", "**"), locals=local)
    except Exception as exc:
        result.error = f"cannot parse expression: {exc}"
        return result

    try:
        expr = sp.simplify(expr)
        result.simplified = str(expr)
    except Exception:  # pragma: no cover - sympy edge case
        result.simplified = str(expr)

    try:
        real_roots = sp.solve(sp.Eq(expr, 0), symbol)
    except Exception:
        real_roots = []
    for root in real_roots:
        value = _numeric_value(root)
        if value is not None:
            result.roots.append(value)

    try:
        derivative = sp.diff(expr, symbol)
        critical = sp.solve(sp.Eq(derivative, 0), symbol)
        for item in critical:
            value = _numeric_value(item)
            if value is None:
                continue
            y = _numeric_value(expr.subs(symbol, item))
            if y is not None:
                result.extrema.append((value, y))
    except Exception:
        pass

    try:
        y0 = _numeric_value(expr.subs(symbol, 0))
        result.y_intercept = y0
    except Exception:
        pass

    # Vertical asymptotes: denominator zeros that are not removable.
    try:
        numerator, denominator = sp.fraction(sp.together(expr))
        if denominator != 1:
            for item in sp.solve(sp.Eq(denominator, 0), symbol):
                value = _numeric_value(item)
                if value is None:
                    continue
                left = _numeric_value(sp.limit(expr, symbol, value, "-"))
                right = _numeric_value(sp.limit(expr, symbol, value, "+"))
                if left is None or right is None or abs(left) > 1e6 or abs(right) > 1e6:
                    result.vertical_asymptotes.append(value)
    except Exception:
        pass

    try:
        result.symmetric_about_y_axis = bool(sp.simplify(expr.subs(symbol, -symbol) - expr) == 0)
    except Exception:
        pass

    return result


def _numeric_value(expression) -> float | None:
    """Evaluate a SymPy expression to a finite real float, or ``None``."""

    sp = _sympy()
    try:
        value = complex(sp.N(expression, 12))
    except Exception:
        return None
    if abs(value.imag) > 1e-9:
        return None
    real = value.real
    if not math.isfinite(real) or abs(real) > 1e12:
        return None
    return float(real)


@dataclass
class CoordinateStats:
    curves: int = 0
    samples: int = 0
    key_points: int = 0
    x_range: tuple[float, float] = (-5.0, 5.0)
    y_range: tuple[float, float] = (-5.0, 5.0)
    warnings: list[str] = field(default_factory=list)


def _compile(expression: str, variable: str):
    sp = _sympy()
    try:
        source = expression.replace("^", "**")
        source = re.sub(r"\bAbs\(", "abs(", source)
        source = re.sub(r"\bln\(", "log(", source)
        expr = sp.sympify(source)
        func = sp.lambdify(sp.Symbol(variable), expr, modules=["math"])
    except Exception as exc:
        raise RenderError("invalid_expression", f"cannot compile {expression!r}: {exc}") from exc

    def evaluate(value: float) -> float | None:
        try:
            result = float(func(value))
        except Exception:
            return None
        if not math.isfinite(result):
            return None
        return result

    return evaluate


def _nice_step(span: float, target_ticks: int = 8) -> float:
    if span <= 0 or not math.isfinite(span):
        return 1.0
    rough = span / max(target_ticks, 2)
    power = 10 ** math.floor(math.log10(rough))
    for multiplier in (1, 2, 2.5, 5, 10):
        step = multiplier * power
        if step >= rough:
            return step
    return 10 * power


def _axis_ranges(spec: Mapping[str, Any], analyses: list[FunctionAnalysis], evaluators: list[Any]) -> tuple[tuple[float, float], tuple[float, float]]:
    x_range = spec.get("x_range")
    if not x_range:
        domain = spec.get("domain")
        if domain:
            x_range = domain
    if not x_range:
        xs = [x for analysis in analyses for x in analysis.roots]
        xs.extend(x for x, _ in (point for analysis in analyses for point in analysis.extrema))
        if xs:
            low, high = min(xs), max(xs)
            pad = max((high - low) * 0.8, 2.0)
            x_range = [low - pad, high + pad]
        else:
            x_range = [-6.0, 6.0]
    x0, x1 = float(x_range[0]), float(x_range[1])
    if x1 <= x0:
        raise RenderError("invalid_range", "x_range must be increasing")

    y_range = spec.get("y_range")
    if not y_range:
        values: list[float] = []
        for evaluator in evaluators:
            for index in range(401):
                x = x0 + (x1 - x0) * index / 400
                y = evaluator(x)
                if y is not None:
                    values.append(y)
        for analysis in analyses:
            values.extend(y for _, y in analysis.extrema)
            if analysis.y_intercept is not None:
                values.append(analysis.y_intercept)
        if not values:
            y_range = [-5.0, 5.0]
        else:
            values.sort()
            low = values[int(len(values) * 0.03)]
            high = values[int(len(values) * 0.97) - 1] if len(values) > 1 else values[-1]
            if high - low < 1e-6:
                low, high = low - 1.0, high + 1.0
            # Keep the plotted window centred on the features that a student
            # must see (intercepts, extrema) instead of the full tail growth.
            features: list[float] = [0.0]
            for analysis in analyses:
                features.extend(y for _, y in analysis.extrema)
                if analysis.y_intercept is not None:
                    features.append(analysis.y_intercept)
                features.extend([0.0] * len(analysis.roots))
            if len(features) > 1:
                f_low, f_high = min(features), max(features)
                f_span = max(f_high - f_low, 1e-6)
                window = (f_low - 0.5 * f_span - 0.5, f_high + 0.5 * f_span + 0.5)
                if (high - low) > 2.2 * (window[1] - window[0]):
                    low, high = window
            pad = (high - low) * 0.12
            y_range = [low - pad, high + pad]
    y0, y1 = float(y_range[0]), float(y_range[1])
    if y1 <= y0:
        raise RenderError("invalid_range", "y_range must be increasing")
    # Keep the origin visible when it is only slightly outside the data range.
    if y0 > 0 and y0 < (y1 - y0) * 0.35:
        y0 = -0.05 * (y1 - y0)
    if y1 < 0 and -y1 < (y1 - y0) * 0.35:
        y1 = 0.05 * (y1 - y0)
    return (x0, x1), (y0, y1)


def _set_plot_view(canvas: Canvas, x_range: tuple[float, float], y_range: tuple[float, float]) -> None:
    margin_x = 62.0
    margin_y = 54.0
    sx = (canvas.width - 2 * margin_x) / (x_range[1] - x_range[0])
    sy = (canvas.height - 2 * margin_y) / (y_range[1] - y_range[0])
    ox = margin_x - x_range[0] * sx
    oy = canvas.height - margin_y + y_range[0] * sy
    canvas.set_view(sx, sy, ox, oy)


def _draw_axes(canvas: Canvas, x_range: tuple[float, float], y_range: tuple[float, float], spec: Mapping[str, Any]) -> None:
    x0, x1 = x_range
    y0, y1 = y_range
    step_x = _nice_step(x1 - x0, 8)
    step_y = _nice_step(y1 - y0, 7)

    if spec.get("grid"):
        x = math.ceil(x0 / step_x) * step_x
        while x <= x1:
            canvas.line((x, y0), (x, y1), GRID)
            x += step_x
        y = math.ceil(y0 / step_y) * step_y
        while y <= y1:
            canvas.line((x0, y), (x1, y), GRID)
            y += step_y

    # Axes, clamped to the visible area.
    axis_y = min(max(0.0, y0), y1)
    axis_x = min(max(0.0, x0), x1)
    canvas.arrow((x0, axis_y), (x1, axis_y), AXIS, head=9.0)
    canvas.arrow((axis_x, y0), (axis_x, y1), AXIS, head=9.0)
    labels = spec.get("axis_labels") or {}
    canvas.text((x1, axis_y), str(labels.get("x", "x")), size=16, anchor="start", baseline="middle", offset=(6, 0), italic=True)
    canvas.text((axis_x, y1), str(labels.get("y", "y")), size=16, anchor="middle", baseline="middle", offset=(0, -8), italic=True)

    # Ticks + numbers.
    x = math.ceil(x0 / step_x) * step_x
    while x <= x1:
        if abs(x) > step_x * 1e-6:
            tick = 4.0 / max(canvas.scale(), 1e-6)
            canvas.line((x, axis_y - tick * 0.5), (x, axis_y + tick * 0.5), AXIS)
            canvas.text((x, axis_y), _format_tick(x), size=12, color=PALETTE["muted"], offset=(0, 15), baseline="middle")
        x += step_x
    y = math.ceil(y0 / step_y) * step_y
    while y <= y1:
        if abs(y) > step_y * 1e-6:
            tick = 4.0 / max(canvas.scale(), 1e-6)
            canvas.line((axis_x - tick, y), (axis_x + tick, y), AXIS)
            canvas.text((axis_x, y), _format_tick(y), size=12, color=PALETTE["muted"], offset=(-8, 0), anchor="end")
        y += step_y
    canvas.text((axis_x, axis_y), "O", size=12, color=PALETTE["muted"], offset=(-9, 11), anchor="middle")


def _format_tick(value: float) -> str:
    if abs(value) < 1e-9:
        return "0"
    if abs(value) >= 1e5 or abs(value) < 1e-3:
        return f"{value:.1e}"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _sample_curve(evaluator, x0: float, x1: float, *, jump: float, samples: int = 900) -> list[list[Point]]:
    """Sample a curve, splitting it at non-finite values and asymptote jumps."""

    segments: list[list[Point]] = []
    current: list[Point] = []
    previous: float | None = None
    for index in range(samples + 1):
        x = x0 + (x1 - x0) * index / samples
        y = evaluator(x)
        if y is None:
            if len(current) > 1:
                segments.append(current)
            current = []
            previous = None
            continue
        if previous is not None and abs(y - previous) > jump:
            if len(current) > 1:
                segments.append(current)
            current = []
        current.append((x, y))
        previous = y
    if len(current) > 1:
        segments.append(current)
    return segments


def render_coordinate(spec: Mapping[str, Any], canvas: Canvas) -> CoordinateStats:
    """Render ``type=function`` and ``type=coordinate`` specs."""

    stats = CoordinateStats()
    curves_spec: list[dict[str, Any]] = list(spec.get("curves") or [])
    if spec.get("expression"):
        curves_spec.insert(0, {"expr": spec["expression"], "variable": spec.get("variable", "x"), "label": spec.get("title")})
    if not curves_spec:
        raise RenderError("empty_plot", "coordinate/function diagram needs at least one curve or point")

    analyses: list[FunctionAnalysis] = []
    evaluators: list[Any] = []
    compiled: list[tuple[dict[str, Any], Any]] = []
    for entry in curves_spec:
        expression = str(entry.get("expr"))
        variable = str(entry.get("variable") or spec.get("variable") or "x")
        evaluator = _compile(expression, variable)
        analysis = analyze_expression(expression, variable)
        if analysis.error:
            stats.warnings.append(analysis.error)
        analyses.append(analysis)
        evaluators.append(evaluator)
        compiled.append((entry, evaluator))

    x_range, y_range = _axis_ranges(spec, analyses, evaluators)
    stats.x_range, stats.y_range = x_range, y_range
    _set_plot_view(canvas, x_range, y_range)
    _draw_axes(canvas, x_range, y_range, spec)

    # Curves
    jump_limit = (y_range[1] - y_range[0]) * 0.75
    for index, (entry, evaluator) in enumerate(compiled):
        domain = entry.get("domain")
        lo, hi = (float(domain[0]), float(domain[1])) if domain else x_range
        segments = _sample_curve(evaluator, lo, hi, jump=jump_limit)
        style = CURVE if index == 0 else CURVE2
        if entry.get("style") == "dashed":
            style = Style(stroke=style.stroke, width=style.width, dash="7 5")
        for segment in segments:
            canvas.polyline(segment, style)
            stats.samples += len(segment)
        stats.curves += 1

        if entry.get("label"):
            visible = [
                position
                for segment in segments
                for position in segment
                if 24 <= canvas.to_screen(position)[0] <= canvas.width - 24
                and 30 <= canvas.to_screen(position)[1] <= canvas.height - 24
            ]
            if visible:
                tail = visible[-1]
                tail_x = canvas.to_screen(tail)[0]
                anchor = "end" if tail_x > canvas.width - 150 else "start"
                offset = (-6, -8) if anchor == "end" else (6, -8)
                canvas.text(tail, str(entry["label"]), size=13, color=style.stroke, anchor=anchor, offset=offset)

    # Key points from symbolic analysis (only when asked, to keep plots tidy).
    if spec.get("mark_key_points"):
        main = analyses[0]
        for root in main.roots:
            if x_range[0] <= root <= x_range[1] and y_range[0] <= 0 <= y_range[1]:
                _key_point(canvas, (root, 0.0), f"({_format_tick(root)}, 0)")
                stats.key_points += 1
        for x, y in main.extrema:
            if x_range[0] <= x <= x_range[1] and y_range[0] <= y <= y_range[1]:
                _key_point(canvas, (x, y), f"({_format_tick(x)}, {_format_tick(y)})")
                stats.key_points += 1
        if main.y_intercept is not None and y_range[0] <= main.y_intercept <= y_range[1]:
            _key_point(canvas, (0.0, main.y_intercept), f"(0, {_format_tick(main.y_intercept)})")
            stats.key_points += 1

    # Explicit guides and points from the spec.
    for guide in spec.get("guides") or []:
        start = (float(guide["from"][0]), float(guide["from"][1]))
        end = (float(guide["to"][0]), float(guide["to"][1]))
        canvas.line(start, end, GUIDE)
    for point in spec.get("points") or []:
        location = (float(point["x"]), float(point["y"]))
        if point.get("style") == "open":
            canvas.dot(location, 4.6, "#ffffff")
            canvas.circle(location, 4.6 / max(canvas.scale(), 1e-6), Style(stroke=PALETTE["accent2"], width=1.6))
        else:
            canvas.dot(location, 4.4, PALETTE["accent2"])
        if point.get("label"):
            canvas.text(
                location,
                str(point["label"]),
                size=13,
                color=PALETTE["accent2"],
                offset=(8, -14),
                anchor="start",
                background="#ffffff",
            )
        stats.key_points += 1

    if spec.get("title"):
        canvas.text_screen(
            (24, 26), str(spec["title"]), size=16, anchor="start", baseline="middle", bold=True, background="#ffffff"
        )
    return stats


def _key_point(canvas: Canvas, point: Point, label: str) -> None:
    canvas.dot(point, 4.2, PALETTE["highlight"])
    canvas.text(
        point,
        label,
        size=12,
        color=PALETTE["highlight"],
        offset=(9, -13),
        anchor="start",
        background="#ffffff",
    )


def render_chart(spec: Mapping[str, Any], canvas: Canvas) -> CoordinateStats:
    """Simple line/bar/scatter chart for data-driven problems."""

    stats = CoordinateStats()
    series = spec.get("series") or []
    if not series:
        raise RenderError("empty_chart", "chart needs at least one series")
    xs = [float(point[0]) for item in series for point in item["points"]]
    ys = [float(point[1]) for item in series for point in item["points"]]
    kind = spec.get("kind") or "line"
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if kind == "bar":
        # Bars are measured from the x-axis, so the origin must stay visible.
        y0, y1 = min(y0, 0.0), max(y1, 0.0)
    if x1 <= x0:
        x1 = x0 + 1.0
    if y1 <= y0:
        y1 = y0 + 1.0
    pad_y = (y1 - y0) * 0.12
    x_range, y_range = (x0 - (x1 - x0) * 0.05, x1 + (x1 - x0) * 0.05), (y0 - pad_y, y1 + pad_y)
    stats.x_range, stats.y_range = x_range, y_range
    _set_plot_view(canvas, x_range, y_range)
    _draw_axes(canvas, x_range, y_range, spec)

    colors = [PALETTE["accent"], PALETTE["highlight"], PALETTE["green"], PALETTE["accent2"]]
    for index, item in enumerate(series):
        color = colors[index % len(colors)]
        points = [(float(point[0]), float(point[1])) for point in item["points"]]
        if kind == "bar":
            width = (x_range[1] - x_range[0]) / max(len(points) * 3, 6)
            for x, y in points:
                canvas.polygon(
                    [(x - width / 2, 0), (x + width / 2, 0), (x + width / 2, y), (x - width / 2, y)],
                    Style(fill=color, stroke=color, width=1.0, opacity=0.75),
                )
        else:
            if kind == "line":
                canvas.polyline(sorted(points), Style(stroke=color, width=2.2))
            for x, y in points:
                canvas.dot((x, y), 4.2, color)
        if item.get("label"):
            last = sorted(points)[-1]
            canvas.text(last, str(item["label"]), size=13, color=color, offset=(8, -12), anchor="start")
        stats.curves += 1
    if spec.get("title"):
        canvas.text_screen((24, 26), str(spec["title"]), size=16, anchor="start", baseline="middle", bold=True)
    return stats
