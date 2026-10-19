"""Entry point: ``python -m exam_solver`` reads one JSON request from stdin.

Examples
--------
    echo '{"op":"ping","payload":{}}' | python -m exam_solver
    python -m exam_solver --selftest
"""

from __future__ import annotations

import json
import sys

from .ops import ensure_utf8_io, handle_request, read_request, write_response


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    ensure_utf8_io()

    if "--version" in args:
        from . import __version__

        print(__version__)
        return 0

    if "--selftest" in args:
        request = {"op": "status", "payload": {}}
        response = handle_request(request)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0 if response.get("ok") else 1

    try:
        request = read_request(sys.stdin)
    except Exception as exc:  # pragma: no cover - malformed pipe
        write_response({"ok": False, "error": {"code": "invalid_request", "message": str(exc)}}, sys.stdout)
        return 2

    response = handle_request(request)
    write_response(response, sys.stdout)
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
