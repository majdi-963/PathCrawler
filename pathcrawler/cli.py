"""Command-line interface for PathCrawler."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from pathcrawler.config import (
    build_scan_config,
    load_config_file,
    parse_extension_argument,
    parse_header_arguments,
    parse_status_argument,
)
from pathcrawler.errors import ConfigurationError, PathCrawlerError
from pathcrawler.logger import setup_logging
from pathcrawler.models import VERSION
from pathcrawler.reporter import print_banner, print_results, print_summary, write_report
from pathcrawler.scanner import PathCrawlerScanner


ETHICAL_NOTICE = (
    "Ethical use notice: PathCrawler is intended ONLY for authorized security "
    "testing against systems you own or have explicit permission to assess."
)


class PathCrawlerArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports errors without Python tracebacks."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        raise ConfigurationError(message)


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface."""

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if not hasattr(args, "func"):
            parser.print_help()
            return 0
        return int(args.func(args))
    except PathCrawlerError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n[ERROR] Scan interrupted by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        logging.debug("Unexpected error", exc_info=True)
        print(f"[ERROR] Unexpected error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the root argparse parser."""

    parser = PathCrawlerArgumentParser(
        prog="python main.py",
        description=f"PathCrawler - Web Directory and File Enumeration Tool\n\n{ETHICAL_NOTICE}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --version\n"
            "  python main.py scan --url http://127.0.0.1:8000 --wordlist wordlists/common.txt\n"
            "  python main.py scan -u https://example.test -w wordlists/common.txt -e php,html -t 20\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"PathCrawler {VERSION}")

    subparsers = parser.add_subparsers(dest="command")
    scan_parser = subparsers.add_parser(
        "scan",
        help="Run an authorized path enumeration scan",
        description=(
            "Run an HTTP path enumeration scan using a user-provided wordlist.\n\n"
            f"{ETHICAL_NOTICE}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py scan --url http://127.0.0.1:8000 --wordlist wordlists/common.txt\n"
            "  python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt -e php,html,txt\n"
            "  python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt -o reports/scan.json\n"
        ),
    )
    scan_parser.set_defaults(func=run_scan)
    scan_parser.add_argument("--url", "-u", dest="target_url", help="Target base URL, for example http://127.0.0.1:8000")
    scan_parser.add_argument("--wordlist", "-w", dest="wordlist_path", help="Path to wordlist file")
    scan_parser.add_argument("--threads", "-t", type=int, help="Number of worker threads, 1 to 100 (default: 10)")
    scan_parser.add_argument("--timeout", "-T", type=float, help="Request timeout in seconds (default: 5)")
    scan_parser.add_argument("--extensions", "-e", help="Comma-separated extensions, for example php,html,txt,bak")
    scan_parser.add_argument("--status", help="Comma-separated status codes to include, for example 200,301,302,403")
    scan_parser.add_argument("--exclude-status", help="Comma-separated status codes to exclude, for example 404")
    scan_parser.add_argument("--output", "-o", dest="output_path", help="Write report to .json or .csv file")
    scan_parser.add_argument("--config", help="Load scan settings from a JSON configuration file")
    scan_parser.add_argument("--recursive", "-r", action="store_true", default=None, help="Recursively scan discovered directory-like paths")
    scan_parser.add_argument("--depth", type=int, help="Maximum recursion depth, 0 to 5 (default: 1)")
    scan_parser.add_argument("--user-agent", help="Custom User-Agent header")
    scan_parser.add_argument("--header", action="append", help="Custom header, repeatable. Format: 'Name: value'")
    scan_parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging level")
    scan_parser.add_argument("--no-follow-redirects", action="store_true", default=None, help="Record redirects without following them")
    scan_parser.add_argument("--delay", type=float, help="Optional delay between requests in seconds")
    return parser


def run_scan(args: argparse.Namespace) -> int:
    """Execute the scan subcommand."""

    cli_values = _cli_values(args)
    config_values = load_config_file(args.config)
    config = build_scan_config(cli_values, config_values)
    setup_logging(config.log_level)

    logging.debug("Starting authorized scan")
    print_banner(config)
    scanner = PathCrawlerScanner(config)
    results, stats, wordlist_stats, _baseline = scanner.scan()
    print_results(results)

    report_path = None
    if config.output_path:
        report_path = write_report(config.output_path, config, stats, results, wordlist_stats)
    print_summary(stats, report_path)
    return 0


def _cli_values(args: argparse.Namespace) -> dict[str, Any]:
    try:
        status_codes = parse_status_argument(args.status)
        exclude_status = parse_status_argument(args.exclude_status)
        extensions = parse_extension_argument(args.extensions)
        headers = parse_header_arguments(args.header)
    except ConfigurationError:
        raise

    values: dict[str, Any] = {
        "target_url": args.target_url,
        "wordlist_path": args.wordlist_path,
        "threads": args.threads,
        "timeout": args.timeout,
        "extensions": extensions,
        "status_codes": status_codes,
        "exclude_status": exclude_status,
        "output_path": args.output_path,
        "recursive": args.recursive,
        "depth": args.depth,
        "user_agent": args.user_agent,
        "headers": headers,
        "log_level": args.log_level,
        "delay": args.delay,
    }
    if args.no_follow_redirects is not None:
        values["follow_redirects"] = not args.no_follow_redirects
    return values
