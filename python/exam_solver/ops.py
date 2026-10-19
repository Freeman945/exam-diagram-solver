"""Operation layer: a JSON-in / JSON-out protocol used by the Node host plugin.

Keeping every capability behind one versioned request shape makes the bridge
trivial to test (``echo '{...}' | python -m exam_solver``) and keeps the Node
side free of scientific dependencies.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from . import __version__
from .diagrams.coordinate import analyze_expression
from .diagrams.render import check_references, render_diagram, validate_diagram_spec
from .errors import EngineError, SpecError
from .examiner import grade_answer
from .schema import format_errors, load_schema, sanitize, validate
from .validators import merge_reports, validate_diagram, validate_math, validate_physics

__all__ = ["dispatch", "OPS", "handle_request"]

OPS: dict[str, Callable[[Mapping[str, Any]], Any]] = {}


def _op(name: str):
    def decorator(function: Callable[[Mapping[str, Any]], Any]):
        OPS[name] = function
        return function

    return decorator


def _string(payload: Mapping[str, Any], key: str, default: str | None = None) -> str:
    value = payload.get(key, default)
    if value is None:
        raise EngineError(f"missing required field {key!r}", code="invalid_request")
    return str(value)


# --------------------------------------------------------------------- status


@_op("ping")
def _ping(_: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "pong": True,
        "engine_version": __version__,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
    }


@_op("status")
def _status(_: Mapping[str, Any]) -> dict[str, Any]:
    features = {"sympy": False, "matplotlib": False, "json_schema_validator": True}
    versions: dict[str, str] = {}
    try:
        import sympy

        features["sympy"] = True
        versions["sympy"] = sympy.__version__
    except Exception:
        pass
    try:
        import matplotlib

        features["matplotlib"] = True
        versions["matplotlib"] = matplotlib.__version__
    except Exception:
        pass
    return {
        "engine_version": __version__,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "features": features,
        "versions": versions,
    }


# -------------------------------------------------------------------- schemas


@_op("validate_spec")
def _validate_spec(payload: Mapping[str, Any]) -> dict[str, Any]:
    kind = _string(payload, "kind", "diagram")
    schema_name = {
        "problem": "problem_spec",
        "problem_spec": "problem_spec",
        "diagram": "diagram_spec",
        "diagram_spec": "diagram_spec",
        "answer": "answer_spec",
        "answer_spec": "answer_spec",
        "exam_report": "exam_report",
        "validation_report": "validation_report",
    }.get(kind)
    if schema_name is None:
        raise EngineError(f"unknown spec kind {kind!r}", code="invalid_request")
    instance = payload.get("spec")
    if not isinstance(instance, Mapping):
        raise EngineError("'spec' must be a JSON object", code="invalid_request")
    schema = load_schema(schema_name)
    cleaned = sanitize(dict(instance), schema)
    errors = validate(cleaned, schema)
    removed = sorted(set(instance) - set(cleaned)) if isinstance(instance, Mapping) else []
    return {
        "kind": schema_name,
        "valid": not errors,
        "errors": [error.as_dict() for error in errors],
        "error_summary": format_errors(errors),
        "sanitized": cleaned,
        "removed_top_level_keys": removed,
    }


# ----------------------------------------------------------------- functions


@_op("analyze_function")
def _analyze_function(payload: Mapping[str, Any]) -> dict[str, Any]:
    expression = _string(payload, "expression")
    variable = _string(payload, "variable", "x")
    analysis = analyze_expression(expression, variable)
    return analysis.as_dict()


# -------------------------------------------------------------------- diagrams


@_op("render_diagram")
def _render(payload: Mapping[str, Any]) -> dict[str, Any]:
    spec = payload.get("diagram")
    if not isinstance(spec, Mapping):
        raise EngineError("'diagram' must be a DiagramSpec object", code="invalid_request")
    out_dir = _string(payload, "outDir")
    basename = _string(payload, "basename", "diagram")
    width = int(payload.get("width") or 760)
    height = int(payload.get("height") or 560)
    formats = payload.get("formats") or ["svg", "png"]
    dpi = int(payload.get("dpi") or 140)
    result = render_diagram(
        spec,
        out_dir=out_dir,
        basename=basename,
        width=width,
        height=height,
        formats=tuple(str(item) for item in formats),
        dpi=dpi,
    )
    return result.as_dict()


@_op("validate_diagram")
def _validate_diagram(payload: Mapping[str, Any]) -> dict[str, Any]:
    spec = payload.get("diagram")
    if not isinstance(spec, Mapping):
        raise EngineError("'diagram' must be a DiagramSpec object", code="invalid_request")
    cleaned, errors = validate_diagram_spec(spec)
    if errors:
        raise SpecError(
            f"DiagramSpec does not validate: {format_errors([_DictError(item) for item in errors])}",
            errors=errors,
            kind="diagram_spec",
        )
    reference_errors = check_references(cleaned)
    if reference_errors:
        raise SpecError(
            f"DiagramSpec references undefined elements: {format_errors([_DictError(item) for item in reference_errors])}",
            errors=reference_errors,
            kind="diagram_spec",
        )
    problem = payload.get("problemSpec") if isinstance(payload.get("problemSpec"), Mapping) else {}
    relations = payload.get("relations")
    report = validate_diagram(cleaned, problem, relations=relations if isinstance(relations, list) else None)
    report["normalized_diagram"] = cleaned
    return report


# ----------------------------------------------------------------- validation


@_op("validate_solution")
def _validate_solution(payload: Mapping[str, Any]) -> dict[str, Any]:
    problem = payload.get("problemSpec")
    answer = payload.get("answerSpec")
    if not isinstance(problem, Mapping) or not isinstance(answer, Mapping):
        raise EngineError("'problemSpec' and 'answerSpec' objects are required", code="invalid_request")
    started = time.perf_counter()
    reports = [validate_math(problem, answer), validate_physics(problem, answer)]
    diagram_spec = payload.get("diagram")
    if isinstance(diagram_spec, Mapping):
        reports.append(validate_diagram(diagram_spec, problem))
    merged = merge_reports(reports)
    merged["duration_ms"] = int((time.perf_counter() - started) * 1000)
    return merged


@_op("grade_answer")
def _grade(payload: Mapping[str, Any]) -> dict[str, Any]:
    problem = payload.get("problemSpec")
    answer = payload.get("answerSpec")
    if not isinstance(problem, Mapping) or not isinstance(answer, Mapping):
        raise EngineError("'problemSpec' and 'answerSpec' objects are required", code="invalid_request")
    report = payload.get("validationReport")
    diagram = payload.get("diagram") if isinstance(payload.get("diagram"), Mapping) else None
    mode = _string(payload, "answerMode", "exam")
    max_score = payload.get("maxScore")
    return grade_answer(
        problem,
        answer,
        report if isinstance(report, Mapping) else None,
        max_score=float(max_score) if max_score else None,
        diagram=diagram,
        answer_mode=mode,
    )


class _DictError:
    def __init__(self, item: Mapping[str, str]) -> None:
        self.path = item.get("path", "$")
        self.message = item.get("message", "")
        self.keyword = item.get("keyword", "")

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message, "keyword": self.keyword}


# -------------------------------------------------------------------- dispatch


def dispatch(op: str, payload: Mapping[str, Any]) -> Any:
    handler = OPS.get(op)
    if handler is None:
        raise EngineError(f"unknown operation {op!r}", code="unknown_op")
    return handler(payload or {})


def handle_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one request or a batch, never raising across the process boundary."""

    if "ops" in request:
        results = []
        for entry in request["ops"]:
            results.append(_execute(entry.get("op"), entry.get("payload") or {}))
        return {"ok": all(item.get("ok") for item in results), "results": results}
    return _execute(request.get("op"), request.get("payload") or {})


def _execute(op: Any, payload: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        if not isinstance(op, str) or not isinstance(payload, Mapping):
            raise EngineError("request must contain a string 'op' and an object 'payload'", code="invalid_request")
        data = dispatch(op, payload)
        return {
            "ok": True,
            "op": op,
            "data": data,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    except EngineError as exc:
        return {"ok": False, "op": op, "error": exc.as_dict(), "duration_ms": int((time.perf_counter() - started) * 1000)}
    except Exception as exc:  # pragma: no cover - defensive boundary
        import traceback

        return {
            "ok": False,
            "op": op,
            "error": {
                "code": "internal_error",
                "message": f"{type(exc).__name__}: {exc}",
                "details": traceback.format_exc(limit=6),
            },
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }


def read_request(stream) -> dict[str, Any]:
    text = stream.read()
    if not text.strip():
        raise EngineError("empty request on stdin", code="invalid_request")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise EngineError(f"request is not valid JSON: {exc}", code="invalid_request") from exc


def write_response(payload: Mapping[str, Any], stream) -> None:
    # ASCII-escaped JSON survives any console code page, so the bridge can
    # never corrupt Chinese text on the way to Node.
    stream.write(json.dumps(payload, ensure_ascii=True))
    stream.write("\n")
    stream.flush()


def ensure_utf8_io() -> None:
    """Windows consoles default to a legacy code page; force UTF-8 pipes."""

    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def default_out_dir(base: str) -> str:
    return str(Path(base))
