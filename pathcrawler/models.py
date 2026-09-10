"""Shared data models for PathCrawler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


VERSION = "1.0.0"


@dataclass
class WordlistStats:
    """Statistics collected while loading a wordlist."""

    path: str
    total_lines: int = 0
    loaded: int = 0
    duplicates: int = 0
    comments: int = 0
    empty: int = 0


@dataclass
class ScanConfig:
    """Validated scan configuration."""

    target_url: str
    wordlist_path: str
    threads: int = 10
    timeout: float = 5.0
    extensions: List[str] = field(default_factory=list)
    status_codes: List[int] = field(default_factory=lambda: [200, 301, 302, 403])
    exclude_status: List[int] = field(default_factory=list)
    output_path: Optional[str] = None
    recursive: bool = False
    depth: int = 1
    user_agent: str = "PathCrawler/1.0"
    headers: Dict[str, str] = field(default_factory=dict)
    log_level: str = "INFO"
    follow_redirects: bool = True
    delay: float = 0.0


@dataclass
class HTTPResponse:
    """Normalized HTTP response data."""

    url: str
    status_code: Optional[int]
    headers: Dict[str, str] = field(default_factory=dict)
    content_length: int = 0
    content_type: str = ""
    body: bytes = b""
    response_time: float = 0.0
    final_url: str = ""
    redirect_location: Optional[str] = None
    original_status_code: Optional[int] = None
    error: Optional[str] = None
    timed_out: bool = False
    redirect_chain: List[str] = field(default_factory=list)


@dataclass
class ScanResult:
    """One scanned path and its analysis result."""

    url: str
    path: str
    status_code: Optional[int]
    content_length: int
    content_type: str
    redirect_location: Optional[str]
    response_time: float
    classification: str
    error: Optional[str] = None


@dataclass
class ScanStatistics:
    """Runtime scan counters."""

    requests: int = 0
    found: int = 0
    errors: int = 0
    timeouts: int = 0
    false_positives: int = 0
    started_at: str = ""
    completed_at: str = ""
    duration: float = 0.0
