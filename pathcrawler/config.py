"""Configuration loading, merging, and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from pathcrawler.errors import ConfigurationError
from pathcrawler.http_client import validate_base_url
from pathcrawler.logger import LOG_LEVELS
from pathcrawler.models import ScanConfig
from pathcrawler.wordlist import normalize_extensions


DEFAULTS: Dict[str, Any] = {
    "threads": 10,
    "timeout": 5,
    "follow_redirects": True,
    "recursive": False,
    "depth": 1,
    "extensions": [],
    "status_codes": [200, 301, 302, 403],
    "exclude_status": [],
    "user_agent": "PathCrawler/1.0",
    "headers": {},
    "log_level": "INFO",
    "delay": 0.0,
}


def load_config_file(path: Optional[str]) -> Dict[str, Any]:
    """Load JSON configuration from disk."""

    if not path:
        return {}

    config_path = Path(path)
    if not config_path.exists():
        raise ConfigurationError("Configuration file not found.")
    if not config_path.is_file():
        raise ConfigurationError("Configuration path is not a file.")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON configuration: {exc.msg}.") from exc
    except PermissionError as exc:
        raise ConfigurationError("Configuration file is not readable.") from exc
    except OSError as exc:
        raise ConfigurationError(f"Could not read configuration: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError("Configuration file must contain a JSON object.")
    return data


def build_scan_config(cli_values: Dict[str, Any], file_values: Optional[Dict[str, Any]] = None) -> ScanConfig:
    """Merge defaults, JSON config, and CLI values into a validated ScanConfig."""

    merged: Dict[str, Any] = dict(DEFAULTS)
    if file_values:
        merged.update(file_values)
    for key, value in cli_values.items():
        if value is not None:
            merged[key] = value

    try:
        target_url = validate_base_url(str(merged.get("target_url", "")).strip())
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc

    wordlist_path = str(merged.get("wordlist_path", "")).strip()
    if not wordlist_path:
        raise ConfigurationError("Wordlist is required.")

    threads = _int_range(merged.get("threads"), "threads", 1, 100)
    timeout = _positive_float(merged.get("timeout"), "timeout")
    if not Path(wordlist_path).exists():
        raise ConfigurationError("Wordlist not found.")
    if not Path(wordlist_path).is_file():
        raise ConfigurationError("Wordlist path is not a file.")
    delay = _non_negative_float(merged.get("delay"), "delay")
    depth = _int_range(merged.get("depth"), "depth", 0, 5)
    log_level = str(merged.get("log_level", "INFO")).upper()
    if log_level not in LOG_LEVELS:
        raise ConfigurationError("Invalid log level. Use DEBUG, INFO, WARNING, or ERROR.")

    extensions = _parse_extensions(merged.get("extensions", []))
    status_codes = _parse_status_codes(merged.get("status_codes", []), "status")
    exclude_status = _parse_status_codes(merged.get("exclude_status", []), "exclude-status")
    headers = _parse_headers(merged.get("headers", {}))

    return ScanConfig(
        target_url=target_url,
        wordlist_path=wordlist_path,
        threads=threads,
        timeout=timeout,
        extensions=extensions,
        status_codes=status_codes,
        exclude_status=exclude_status,
        output_path=merged.get("output_path"),
        recursive=bool(merged.get("recursive", False)),
        depth=depth,
        user_agent=str(merged.get("user_agent") or DEFAULTS["user_agent"]),
        headers=headers,
        log_level=log_level,
        follow_redirects=bool(merged.get("follow_redirects", True)),
        delay=delay,
    )


def parse_status_argument(value: Optional[str]) -> Optional[list[int]]:
    """Parse a comma-separated status-code CLI value."""

    if value is None:
        return None
    return _parse_status_codes(value, "status")


def parse_extension_argument(value: Optional[str]) -> Optional[list[str]]:
    """Parse a comma-separated extension CLI value."""

    if value is None:
        return None
    return _parse_extensions(value)


def parse_header_arguments(values: Optional[list[str]]) -> Optional[dict[str, str]]:
    """Parse repeated 'Name: value' header arguments."""

    if values is None:
        return None
    parsed: dict[str, str] = {}
    for header in values:
        if ":" not in header:
            raise ConfigurationError("Malformed custom header. Use 'Name: value'.")
        name, value = header.split(":", 1)
        name = name.strip()
        value = value.strip()
        if not name or any(ch in name for ch in "\r\n:"):
            raise ConfigurationError("Malformed custom header name.")
        if any(ch in value for ch in "\r\n"):
            raise ConfigurationError("Malformed custom header value.")
        parsed[name] = value
    return parsed


def _parse_extensions(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        raise ConfigurationError("Extensions must be a comma-separated string or list.")
    try:
        return normalize_extensions(str(part) for part in parts)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc


def _parse_status_codes(value: Any, label: str) -> list[int]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, Iterable):
        raw_items = list(value)
    else:
        raise ConfigurationError(f"Invalid {label} code list.")

    codes: list[int] = []
    seen: set[int] = set()
    for item in raw_items:
        try:
            code = int(str(item).strip())
        except ValueError as exc:
            raise ConfigurationError(f"Invalid {label} code: {item}.") from exc
        if code < 100 or code > 599:
            raise ConfigurationError(f"Invalid {label} code: {code}.")
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _parse_headers(value: Any) -> dict[str, str]:
    if value in (None, "", []):
        return {}
    if isinstance(value, dict):
        headers = value
    elif isinstance(value, list):
        return parse_header_arguments([str(item) for item in value]) or {}
    else:
        raise ConfigurationError("Headers must be an object or a list of 'Name: value' strings.")
    parsed: dict[str, str] = {}
    for name, header_value in headers.items():
        header_name = str(name).strip()
        header_text = str(header_value).strip()
        if not header_name or any(ch in header_name for ch in "\r\n:"):
            raise ConfigurationError("Malformed custom header name.")
        if any(ch in header_text for ch in "\r\n"):
            raise ConfigurationError("Malformed custom header value.")
        parsed[header_name] = header_text
    return parsed


def _int_range(value: Any, name: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid {name}.") from exc
    if number < minimum or number > maximum:
        raise ConfigurationError(f"Invalid {name}. Use a value from {minimum} to {maximum}.")
    return number


def _positive_float(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid {name}.") from exc
    if number <= 0:
        raise ConfigurationError(f"Invalid {name}. Use a positive value.")
    return number


def _non_negative_float(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid {name}.") from exc
    if number < 0:
        raise ConfigurationError(f"Invalid {name}. Use zero or a positive value.")
    return number
