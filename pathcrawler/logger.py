"""Logging setup for PathCrawler."""

from __future__ import annotations

import logging
import sys


LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


def setup_logging(level: str) -> None:
    """Configure console logging."""

    normalized = (level or "INFO").upper()
    if normalized not in LOG_LEVELS:
        normalized = "INFO"

    logging.basicConfig(
        level=getattr(logging, normalized),
        format="[%(levelname)s] %(message)s",
        stream=sys.stderr,
        force=True,
    )


def mask_headers(headers: dict[str, str]) -> dict[str, str]:
    """Mask sensitive headers for non-debug logs."""

    sensitive = {"authorization", "cookie", "proxy-authorization", "x-api-key"}
    masked: dict[str, str] = {}
    for name, value in headers.items():
        if name.lower() in sensitive:
            masked[name] = "<masked>"
        else:
            masked[name] = value
    return masked
