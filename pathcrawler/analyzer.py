"""Response analysis and filtering."""

from __future__ import annotations

from typing import Optional

from pathcrawler.models import HTTPResponse, ScanConfig, ScanResult


ERROR = "ERROR"
FOUND = "FOUND"
FORBIDDEN = "FORBIDDEN"
LIKELY_FALSE_POSITIVE = "LIKELY_FALSE_POSITIVE"
NOT_FOUND = "NOT_FOUND"
REDIRECT = "REDIRECT"


def display_status(response: HTTPResponse) -> Optional[int]:
    """Return the status code most useful for enumeration output."""

    return response.original_status_code or response.status_code


class ResponseAnalyzer:
    """Classifies HTTP responses using status filters and a custom 404 baseline."""

    def __init__(
        self, config: ScanConfig, baseline: Optional[HTTPResponse] = None
    ) -> None:
        self.config = config
        self.baseline = baseline

    def analyze(self, path: str, response: HTTPResponse) -> ScanResult:
        """Convert HTTP response metadata into a classified scan result."""

        status = display_status(response)
        if response.error:
            classification = ERROR
        elif status is not None and 300 <= status < 400:
            classification = REDIRECT
        elif status in {401, 403}:
            classification = FORBIDDEN
        elif self._matches_false_positive(response):
            classification = LIKELY_FALSE_POSITIVE
        elif status is not None and status < 400:
            classification = FOUND
        else:
            classification = NOT_FOUND

        return ScanResult(
            url=response.url,
            path=path,
            status_code=status,
            content_length=response.content_length,
            content_type=response.content_type,
            redirect_location=response.redirect_location,
            response_time=response.response_time,
            classification=classification,
            error=response.error,
        )

    def should_include(self, result: ScanResult) -> bool:
        """Apply include and exclude status filters to a result."""

        if result.classification == ERROR:
            return False
        if result.status_code is None:
            return False
        if result.status_code in self.config.exclude_status:
            return False
        if self.config.status_codes:
            return result.status_code in self.config.status_codes
        return result.classification != NOT_FOUND

    def _matches_false_positive(self, response: HTTPResponse) -> bool:
        if self.baseline is None or self.baseline.error:
            return False

        response_status = display_status(response)
        baseline_status = display_status(self.baseline)
        if response_status is None or baseline_status is None:
            return False
        if response_status != baseline_status:
            return False
        if response_status in {401, 403} or 300 <= response_status < 400:
            return False
        if response_status == 404:
            return True

        response_type = response.content_type.split(";", 1)[0].strip().lower()
        baseline_type = self.baseline.content_type.split(";", 1)[0].strip().lower()
        if response_type and baseline_type and response_type != baseline_type:
            return False

        allowed_difference = max(64, int(max(self.baseline.content_length, 1) * 0.08))
        length_difference = abs(response.content_length - self.baseline.content_length)
        return length_difference <= allowed_difference
