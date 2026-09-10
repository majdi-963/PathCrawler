"""Concurrent path enumeration scanner."""

from __future__ import annotations

import logging
import random
import string
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Iterable, List, Tuple

from pathcrawler.analyzer import (
    ERROR,
    FOUND,
    FORBIDDEN,
    LIKELY_FALSE_POSITIVE,
    REDIRECT,
    ResponseAnalyzer,
)
from pathcrawler.http_client import HTTPClient, build_url
from pathcrawler.models import HTTPResponse, ScanConfig, ScanResult, ScanStatistics, WordlistStats
from pathcrawler.wordlist import generate_paths, load_wordlist


class PathCrawlerScanner:
    """Coordinates baseline detection, concurrent requests, and recursion."""

    def __init__(self, config: ScanConfig) -> None:
        self.config = config
        self.client = HTTPClient(
            timeout=config.timeout,
            user_agent=config.user_agent,
            headers=config.headers,
            follow_redirects=config.follow_redirects,
        )
        self._request_lock = threading.Lock()
        self._last_request_time = 0.0
        self._scanned_paths: set[str] = set()

    def scan(self) -> Tuple[List[ScanResult], ScanStatistics, WordlistStats, HTTPResponse]:
        """Run a full scan and return included results, statistics, wordlist stats, and baseline."""

        words, wordlist_stats = load_wordlist(self.config.wordlist_path)
        stats = ScanStatistics(started_at=_utc_now())
        start = time.perf_counter()

        baseline_path = self._random_baseline_path()
        baseline_response = self._fetch_path(baseline_path, include_body=False)
        stats.requests += 1
        if baseline_response.timed_out:
            stats.timeouts += 1
        if baseline_response.error:
            stats.errors += 1

        analyzer = ResponseAnalyzer(self.config, baseline_response)
        included_results: List[ScanResult] = []
        current_prefixes = [""]

        max_depth = self.config.depth if self.config.recursive else 0
        for depth in range(max_depth + 1):
            prefixes_to_scan = current_prefixes
            current_prefixes = []
            candidate_paths = self._new_paths(generate_paths(words, self.config.extensions, prefixes_to_scan[0])) if len(prefixes_to_scan) == 1 else []
            if len(prefixes_to_scan) > 1:
                all_paths: list[str] = []
                for prefix in prefixes_to_scan:
                    all_paths.extend(generate_paths(words, self.config.extensions, prefix))
                candidate_paths = self._new_paths(all_paths)

            if not candidate_paths:
                continue

            logging.debug("Scanning %d paths at depth %d", len(candidate_paths), depth)
            depth_results = self._scan_paths(candidate_paths, analyzer, stats)
            for result in depth_results:
                if analyzer.should_include(result):
                    included_results.append(result)
                if depth < max_depth and self._is_recursive_candidate(result):
                    current_prefixes.append(result.path)

            current_prefixes = _unique(current_prefixes)
            if not self.config.recursive or not current_prefixes:
                break

        stats.completed_at = _utc_now()
        stats.duration = time.perf_counter() - start
        stats.found = sum(
            1
            for result in included_results
            if result.classification in {FOUND, FORBIDDEN, REDIRECT}
        )
        stats.errors = max(stats.errors, sum(1 for result in included_results if result.classification == ERROR))
        stats.false_positives = sum(
            1 for result in included_results if result.classification == LIKELY_FALSE_POSITIVE
        )

        return included_results, stats, wordlist_stats, baseline_response

    def _scan_paths(
        self,
        paths: Iterable[str],
        analyzer: ResponseAnalyzer,
        stats: ScanStatistics,
    ) -> List[ScanResult]:
        results: List[ScanResult] = []
        with ThreadPoolExecutor(max_workers=self.config.threads) as executor:
            future_to_path = {
                executor.submit(self._fetch_path, path, False): path
                for path in paths
            }
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    response = future.result()
                except Exception as exc:  # Defensive guard for unexpected worker failures.
                    logging.debug("Worker failed for %s", path, exc_info=True)
                    response = HTTPResponse(
                        url=build_url(self.config.target_url, path),
                        status_code=None,
                        error=f"Unexpected scanner error: {exc}",
                    )
                stats.requests += 1
                if response.timed_out:
                    stats.timeouts += 1
                if response.error:
                    stats.errors += 1
                result = analyzer.analyze(path, response)
                results.append(result)
        results.sort(key=lambda item: item.path)
        return results

    def _fetch_path(self, path: str, include_body: bool = False) -> HTTPResponse:
        self._respect_delay()
        return self.client.get(build_url(self.config.target_url, path), include_body=include_body)

    def _respect_delay(self) -> None:
        if self.config.delay <= 0:
            return
        with self._request_lock:
            now = time.perf_counter()
            wait_time = self.config.delay - (now - self._last_request_time)
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_request_time = time.perf_counter()

    def _new_paths(self, paths: Iterable[str]) -> List[str]:
        new_paths: List[str] = []
        for path in paths:
            if path not in self._scanned_paths:
                self._scanned_paths.add(path)
                new_paths.append(path)
        return new_paths

    def _is_recursive_candidate(self, result: ScanResult) -> bool:
        if result.classification not in {FOUND, FORBIDDEN, REDIRECT}:
            return False
        last_segment = result.path.rstrip("/").rsplit("/", 1)[-1]
        if "." in last_segment:
            return False
        return True

    def _random_baseline_path(self) -> str:
        suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(14))
        return f"/pc-nonexistent-{suffix}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
