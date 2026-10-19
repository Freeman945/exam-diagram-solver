"""Strict, dependency-free JSON Schema validation for the project's own schemas.

The engine deliberately avoids a third-party ``jsonschema`` dependency so the
plugin works on any Python that has SymPy. Only the keywords used by the
schemas in ``schemas/`` are implemented; unknown keywords are ignored.

Two entry points matter at the model boundary:

* :func:`validate` reports every violation with a JSON path.
* :func:`sanitize` repairs a model-produced object against a schema *before*
  validation - it drops unknown keys, coerces obvious scalar mismatches and
  resolves ``oneOf`` branches by best match. This keeps "strict validation"
  strict without turning one hallucinated field into a total failure.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "SchemaError",
    "ValidationError",
    "load_schema",
    "schema_dir",
    "validate",
    "sanitize",
    "format_errors",
    "check",
]

_MAX_DEPTH = 32


@dataclass(frozen=True)
class ValidationError:
    """One schema violation."""

    path: str
    message: str
    keyword: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message, "keyword": self.keyword}


class SchemaError(RuntimeError):
    """Raised when a schema document itself cannot be loaded."""


@dataclass
class _Context:
    root: Mapping[str, Any]
    errors: list[ValidationError] = field(default_factory=list)

    def fail(self, path: str, message: str, keyword: str = "") -> None:
        self.errors.append(ValidationError(path, message, keyword))


def schema_dir() -> Path:
    """Locate the repository ``schemas/`` directory."""

    override = __import__("os").environ.get("EXAM_SOLVER_SCHEMA_DIR")
    if override:
        candidate = Path(override)
        if candidate.is_dir():
            return candidate
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schemas"
        if (candidate / "problem_spec.schema.json").is_file():
            return candidate
    raise SchemaError("cannot locate the schemas/ directory; set EXAM_SOLVER_SCHEMA_DIR")


def load_schema(name: str) -> dict[str, Any]:
    """Load one schema document by file name (with or without ``.json``)."""

    filename = name if name.endswith(".json") else f"{name}.schema.json"
    path = schema_dir() / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - environment failure
        raise SchemaError(f"cannot read schema {path}: {exc}") from exc
    except json.JSONDecodeError as exc:  # pragma: no cover - broken checkout
        raise SchemaError(f"invalid JSON in schema {path}: {exc}") from exc


_TYPE_CHECKS: dict[str, Any] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected: str) -> bool:
    checker = _TYPE_CHECKS.get(expected)
    return bool(checker and checker(value))


def _resolve_ref(ref: str, root: Mapping[str, Any]) -> Mapping[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaError(f"unsupported $ref: {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, Mapping) or part not in node:
            raise SchemaError(f"unresolvable $ref: {ref}")
        node = node[part]
    if not isinstance(node, Mapping):
        raise SchemaError(f"$ref does not point at an object: {ref}")
    return node


def _equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)
    return left == right


def _validate(instance: Any, schema: Mapping[str, Any], ctx: _Context, path: str, depth: int) -> None:
    if depth > _MAX_DEPTH:
        ctx.fail(path, "schema recursion limit exceeded", "depth")
        return

    if "$ref" in schema:
        target = _resolve_ref(str(schema["$ref"]), ctx.root)
        _validate(instance, target, ctx, path, depth + 1)
        return

    if "const" in schema and not _equal(instance, schema["const"]):
        ctx.fail(path, f"must equal {schema['const']!r}", "const")
        return

    if "enum" in schema:
        options = schema["enum"]
        if not any(_equal(instance, option) for option in options):
            ctx.fail(path, f"must be one of {list(options)!r}", "enum")
            return

    if "type" in schema:
        expected = schema["type"]
        types = [expected] if isinstance(expected, str) else list(expected)
        if not any(_matches_type(instance, item) for item in types):
            ctx.fail(path, f"expected {'/'.join(types)}, got {_type_name(instance)}", "type")
            return

    if "oneOf" in schema:
        branches = schema["oneOf"]
        results = []
        for branch in branches:
            sub = _Context(ctx.root)
            _validate(instance, branch, sub, path, depth + 1)
            results.append(sub.errors)
        if not any(len(errors) == 0 for errors in results):
            best = min(results, key=len)
            ctx.fail(path, "does not match any allowed variant", "oneOf")
            for error in best[:6]:
                ctx.errors.append(ValidationError(error.path, f"(closest variant) {error.message}", error.keyword))
            return

    if "anyOf" in schema:
        results = []
        for branch in schema["anyOf"]:
            sub = _Context(ctx.root)
            _validate(instance, branch, sub, path, depth + 1)
            results.append(sub.errors)
        if not any(len(errors) == 0 for errors in results):
            best = min(results, key=len)
            ctx.fail(path, "does not match any allowed variant", "anyOf")
            for error in best[:6]:
                ctx.errors.append(ValidationError(error.path, f"(closest variant) {error.message}", error.keyword))
            return

    if "allOf" in schema:
        for branch in schema["allOf"]:
            _validate(instance, branch, ctx, path, depth + 1)

    if isinstance(instance, dict):
        _validate_object(instance, schema, ctx, path, depth)
    if isinstance(instance, list):
        _validate_array(instance, schema, ctx, path, depth)
    if isinstance(instance, str):
        _validate_string(instance, schema, ctx, path)
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        _validate_number(float(instance), schema, ctx, path)


def _validate_object(instance: dict[str, Any], schema: Mapping[str, Any], ctx: _Context, path: str, depth: int) -> None:
    for key in schema.get("required", []):
        if key not in instance:
            ctx.fail(path, f"missing required property {key!r}", "required")

    properties = schema.get("properties", {})
    for key, value in instance.items():
        child_path = f"{path}.{key}"
        if key in properties:
            _validate(value, properties[key], ctx, child_path, depth + 1)
            continue
        pattern_properties = schema.get("patternProperties", {})
        matched = False
        for pattern, subschema in pattern_properties.items():
            if re.search(pattern, key):
                _validate(value, subschema, ctx, child_path, depth + 1)
                matched = True
        if matched:
            continue
        additional = schema.get("additionalProperties", True)
        if additional is False:
            ctx.fail(path, f"unexpected property {key!r}", "additionalProperties")
        elif isinstance(additional, Mapping):
            _validate(value, additional, ctx, child_path, depth + 1)

    min_properties = schema.get("minProperties")
    if isinstance(min_properties, int) and len(instance) < min_properties:
        ctx.fail(path, f"needs at least {min_properties} properties", "minProperties")


def _validate_array(instance: list[Any], schema: Mapping[str, Any], ctx: _Context, path: str, depth: int) -> None:
    min_items = schema.get("minItems")
    if isinstance(min_items, int) and len(instance) < min_items:
        ctx.fail(path, f"needs at least {min_items} items", "minItems")
    max_items = schema.get("maxItems")
    if isinstance(max_items, int) and len(instance) > max_items:
        ctx.fail(path, f"allows at most {max_items} items", "maxItems")
    items = schema.get("items")
    if isinstance(items, Mapping):
        for index, value in enumerate(instance):
            _validate(value, items, ctx, f"{path}[{index}]", depth + 1)


def _validate_string(instance: str, schema: Mapping[str, Any], ctx: _Context, path: str) -> None:
    min_length = schema.get("minLength")
    if isinstance(min_length, int) and len(instance) < min_length:
        ctx.fail(path, f"needs at least {min_length} characters", "minLength")
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and not re.search(pattern, instance):
        ctx.fail(path, f"does not match pattern {pattern!r}", "pattern")


def _validate_number(instance: float, schema: Mapping[str, Any], ctx: _Context, path: str) -> None:
    minimum = schema.get("minimum")
    if isinstance(minimum, (int, float)) and instance < minimum:
        ctx.fail(path, f"must be >= {minimum}", "minimum")
    maximum = schema.get("maximum")
    if isinstance(maximum, (int, float)) and instance > maximum:
        ctx.fail(path, f"must be <= {maximum}", "maximum")
    exclusive_minimum = schema.get("exclusiveMinimum")
    if isinstance(exclusive_minimum, (int, float)) and instance <= exclusive_minimum:
        ctx.fail(path, f"must be > {exclusive_minimum}", "exclusiveMinimum")


def validate(instance: Any, schema: Mapping[str, Any]) -> list[ValidationError]:
    """Validate ``instance`` and return every violation (empty means valid)."""

    ctx = _Context(root=schema)
    _validate(instance, schema, ctx, "$", 0)
    deduped: list[ValidationError] = []
    seen: set[tuple[str, str]] = set()
    for error in ctx.errors:
        key = (error.path, error.message)
        if key not in seen:
            seen.add(key)
            deduped.append(error)
    return deduped


def check(instance: Any, schema_name: str, *, sanitize_first: bool = True) -> tuple[Any, list[ValidationError]]:
    """Load a schema by name, optionally sanitize, then validate.

    Returns the (possibly repaired) instance and the remaining errors.
    """

    schema = load_schema(schema_name)
    prepared = sanitize(instance, schema) if sanitize_first else instance
    return prepared, validate(prepared, schema)


def format_errors(errors: Iterable[ValidationError], limit: int = 8) -> str:
    """Render errors as a compact, model-readable list."""

    rendered = [f"{error.path}: {error.message}" for error in errors[:limit]]
    if len(list(errors)) > limit:
        rendered.append(f"... {len(list(errors)) - limit} more")
    return "; ".join(rendered)


# --------------------------------------------------------------------------- sanitize


_NUMERIC_PATTERN = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")
_BOOLEAN_PATTERN = re.compile(r"^(true|false)$", re.IGNORECASE)


def _coerce_scalar(value: Any, schema: Mapping[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    expected = schema.get("type")
    types = [expected] if isinstance(expected, str) else list(expected or [])
    if "number" in types or "integer" in types:
        if _NUMERIC_PATTERN.match(value.strip()):
            number = float(value)
            return int(number) if "integer" in types and number.is_integer() else number
    if "boolean" in types and _BOOLEAN_PATTERN.match(value.strip()):
        return value.strip().lower() == "true"
    return value


def _sanitize(instance: Any, schema: Mapping[str, Any], root: Mapping[str, Any], depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return instance

    if "$ref" in schema:
        return _sanitize(instance, _resolve_ref(str(schema["$ref"]), root), root, depth + 1)

    branches = schema.get("oneOf") or schema.get("anyOf")
    if isinstance(branches, list):
        if isinstance(instance, dict):
            discriminator = instance.get("type")
            if isinstance(discriminator, str):
                for branch in branches:
                    target = _resolve_ref(str(branch["$ref"]), root) if "$ref" in branch else branch
                    const = target.get("properties", {}).get("type", {}).get("const")
                    if const == discriminator:
                        return _sanitize(instance, target, root, depth + 1)
        best: tuple[int, Any] | None = None
        for branch in branches:
            target = _resolve_ref(str(branch["$ref"]), root) if "$ref" in branch else branch
            candidate = _sanitize(instance, target, root, depth + 1)
            # Validate against the real root so nested "$ref"s still resolve.
            probe = _Context(root=root)
            _validate(candidate, target, probe, "$", depth + 1)
            score = len(probe.errors)
            if best is None or score < best[0]:
                best = (score, candidate)
        return best[1] if best else instance

    instance = _coerce_scalar(instance, schema)

    properties = schema.get("properties", {})
    if isinstance(instance, dict):
        result: dict[str, Any] = {}
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                result[key] = _sanitize(value, properties[key], root, depth + 1)
            elif isinstance(additional, Mapping):
                result[key] = _sanitize(value, additional, root, depth + 1)
            elif additional is True:
                result[key] = value
            # additionalProperties: false -> drop
        return result

    if isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, Mapping):
            return [_sanitize(value, items, root, depth + 1) for value in instance]
        return instance

    return instance


def sanitize(instance: Any, schema: Mapping[str, Any]) -> Any:
    """Repair an instance against a schema without inventing required content."""

    return _sanitize(instance, schema, schema, 0)


def describe_type(value: Any) -> str:
    """Public helper used in diagnostics."""

    return _type_name(value)
