"""Typed engine errors shared by every operation."""

from __future__ import annotations

from typing import Any

__all__ = ["EngineError", "SpecError", "ValidationFailure"]


class EngineError(RuntimeError):
    """Base class for errors that cross the Python/Node process boundary."""

    code = "engine_error"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        if code:
            self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class SpecError(EngineError):
    """A spec failed strict schema validation."""

    code = "invalid_spec"

    def __init__(self, message: str, *, errors: list[dict[str, str]] | None = None, kind: str = "spec") -> None:
        super().__init__(message, code=f"invalid_{kind}", details={"errors": errors or []})
        self.errors = errors or []


class ValidationFailure(EngineError):
    """A validator could not run (as opposed to a check that failed)."""

    code = "validation_unavailable"
