"""Report writing and console output."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Optional

from pathcrawler.errors import ReportError
from pathcrawler.models import ScanConfig, ScanResult, ScanStatistics, VERSION, WordlistStats


def write_report(
    output_path: str,
    config: ScanConfig,
    stats: ScanStatistics,
    results: Iterable[ScanResult],
    wordlist_stats: WordlistStats,
) -> str:
    """Write JSON or CSV report inferred from the output extension."""

    path = Path(output_path)
    extension = path.suffix.lower()
    if extension not in {".json", ".csv"}:
        raise ReportError("Invalid output path. Use a .json or .csv file.")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReportError(f"Could not create report directory: {exc}") from exc

    result_list = list(results)
    try:
        if extension == ".json":
            _write_json(path, config, stats, result_list, wordlist_stats)
        else:
            _write_csv(path, result_list)
    except PermissionError as exc:
        raise ReportError("Report output path is not writable.") from exc
    except OSError as exc:
        raise ReportError(f"Could not write report: {exc}") from exc

    return str(path)


def print_banner(config: ScanConfig) -> None:
    """Print scan header."""

    print(f"PathCrawler v{VERSION}")
    print()
    print(f"Target       : {config.target_url}")
    print(f"Wordlist     : {config.wordlist_path}")
    print(f"Threads      : {config.threads}")
    print(f"Timeout      : {config.timeout:g}s")
    print(f"Recursive    : {'yes' if config.recursive else 'no'}")
    if config.recursive:
        print(f"Depth        : {config.depth}")
    print()


def print_results(results: Iterable[ScanResult]) -> None:
    """Print readable scan findings."""

    result_list = list(results)
    print("---")
    if not result_list:
        print("No matching paths found.")
    for result in result_list:
        status = result.status_code if result.status_code is not None else "ERR"
        length = f"{result.content_length} B"
        timing = f"{result.response_time:.2f}s"
        line = f"[{status}] {result.path:<28} {length:>10} {timing:>7} {result.classification}"
        if result.redirect_location:
            line += f" -> {result.redirect_location}"
        if result.error:
            line += f" ({result.error})"
        print(line)
    print("---")


def print_summary(stats: ScanStatistics, report_path: Optional[str] = None) -> None:
    """Print end-of-scan statistics."""

    print(f"Requests    : {stats.requests}")
    print(f"Found       : {stats.found}")
    print(f"Errors      : {stats.errors}")
    print(f"Timeouts    : {stats.timeouts}")
    print(f"Duration    : {stats.duration:.2f}s")
    if report_path:
        print()
        print("Report saved:")
        print(report_path)


def _write_json(
    path: Path,
    config: ScanConfig,
    stats: ScanStatistics,
    results: list[ScanResult],
    wordlist_stats: WordlistStats,
) -> None:
    payload = {
        "tool": "PathCrawler",
        "version": VERSION,
        "target": config.target_url,
        "started_at": stats.started_at,
        "completed_at": stats.completed_at,
        "duration": round(stats.duration, 4),
        "requests": stats.requests,
        "findings": stats.found,
        "errors": stats.errors,
        "timeouts": stats.timeouts,
        "wordlist": {
            "path": wordlist_stats.path,
            "loaded": wordlist_stats.loaded,
            "total_lines": wordlist_stats.total_lines,
            "duplicates": wordlist_stats.duplicates,
            "comments": wordlist_stats.comments,
            "empty": wordlist_stats.empty,
        },
        "results": [_result_to_dict(result) for result in results],
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2)


def _write_csv(path: Path, results: list[ScanResult]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "path",
                "url",
                "status_code",
                "content_length",
                "content_type",
                "redirect_location",
                "response_time",
                "classification",
                "error",
            ],
        )
        writer.writeheader()
        for result in results:
            row = _result_to_dict(result)
            row["response_time"] = f"{result.response_time:.4f}"
            writer.writerow(row)


def _result_to_dict(result: ScanResult) -> dict[str, object]:
    return {
        "path": result.path,
        "url": result.url,
        "status_code": result.status_code,
        "content_length": result.content_length,
        "content_type": result.content_type,
        "redirect_location": result.redirect_location,
        "response_time": round(result.response_time, 4),
        "classification": result.classification,
        "error": result.error,
    }
