"""Shared response helpers for routers."""

from typing import Any

from fastapi import HTTPException


def error_response(status_code: int, error_code: str, message: str, details: str | dict[str, Any] | None = None) -> HTTPException:
    """Create a standardized HTTPException payload."""

    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message": message,
            "details": details,
        },
    )
