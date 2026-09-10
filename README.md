# PathCrawler

## Project Overview

PathCrawler is a Python 3 web directory and file enumeration tool for authorized security testing. It reads a user-provided wordlist, generates candidate HTTP paths, requests those paths, classifies the responses, and optionally writes JSON or CSV reports.

This tool is intended ONLY for authorized security testing. Do not run it against systems you do not own or do not have explicit permission to assess.

## Problem Statement

Web applications sometimes expose forgotten directories, backup files, administrative panels, development routes, or static resources. Security testers need a controlled way to identify these paths during reconnaissance without using exploitation payloads or credential attacks.

## Project Idea

PathCrawler performs HTTP path enumeration using standard HTTP GET requests. It combines a target URL with entries from a wordlist, optionally adds file extensions, analyzes status codes and response metadata, and highlights potentially interesting results.

## Project Objectives

- Build a standard-library-only cybersecurity tool in Python 3.
- Demonstrate safe web reconnaissance and HTTP response analysis.
- Support concurrency, timeouts, redirects, configuration, reports, and robust error handling.
- Provide tests and a local demo environment suitable for a university project defense.

## Cybersecurity Relevance

Directory and file enumeration is a common authorized reconnaissance technique. It helps defenders and testers find unintended exposure, verify access controls, and understand a web application's visible attack surface. PathCrawler does not exploit vulnerabilities; its scope is path enumeration only.

## Features

- HTTP and HTTPS GET support through `urllib.request`.
- User-provided wordlist loading with duplicate, blank-line, and comment handling.
- Optional file extension generation such as `.php`, `.html`, `.txt`, and `.bak`.
- Concurrent scanning with `ThreadPoolExecutor`.
- Status include and exclude filters.
- Redirect recording with configurable following.
- Custom User-Agent and custom headers.
- False-positive baseline detection for custom 404 pages.
- Optional recursive scanning with safe depth limits.
- JSON and CSV reports.
- JSON configuration file support.
- Clean CLI errors without normal-user tracebacks.
- Unit tests using `unittest` only.

## Architecture

- `main.py`: executable entry point.
- `pathcrawler/cli.py`: argparse interface and command dispatch.
- `pathcrawler/scanner.py`: scan orchestration, concurrency, recursion, and statistics.
- `pathcrawler/http_client.py`: standard-library HTTP client and URL construction.
- `pathcrawler/wordlist.py`: wordlist loading and path generation.
- `pathcrawler/analyzer.py`: response classification and false-positive checks.
- `pathcrawler/config.py`: JSON config loading and validation.
- `pathcrawler/reporter.py`: terminal, JSON, and CSV reporting.
- `pathcrawler/models.py`: dataclasses used across the project.
- `tests/`: `unittest` test suite.
- `examples/demo_server/`: local demonstration website.

## Requirements

- Python 3.10 or newer recommended.
- No third-party Python packages.
- Works on Linux and Windows.

## Installation

Linux:

```bash
unzip PathCrawler.zip
cd PathCrawler
python main.py --help
```

Windows PowerShell:

```powershell
Expand-Archive .\PathCrawler.zip
cd .\PathCrawler
python .\main.py --help
```

`requirements.txt` is included only to document that no third-party dependencies are required.

## Usage

Show help:

```bash
python main.py --help
python main.py scan --help
```

Show version:

```bash
python main.py --version
```

Run a scan:

```bash
python main.py scan --url http://127.0.0.1:8000 --wordlist wordlists/common.txt
```

## CLI Examples

Use short options:

```bash
python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt
```

Use extensions:

```bash
python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt -e php,html,txt,bak
```

Include only selected status codes:

```bash
python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt --status 200,301,302,403
```

Exclude status codes:

```bash
python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt --exclude-status 404
```

Write JSON and CSV reports:

```bash
python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt -o reports/scan.json
python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt -o reports/scan.csv
```

Use recursion:

```bash
python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt --recursive --depth 2
```

Use custom headers:

```bash
python main.py scan -u http://127.0.0.1:8000 -w wordlists/common.txt --user-agent "PathCrawler/1.0" --header "Authorization: Bearer example"
```

Windows PowerShell examples use the same arguments:

```powershell
python .\main.py scan --url http://127.0.0.1:8000 --wordlist .\wordlists\common.txt
```

## Configuration

Load settings from JSON:

```bash
python main.py scan --config config.json --url http://127.0.0.1:8000 --wordlist wordlists/common.txt
```

Command-line arguments override configuration-file values. Example:

```json
{
  "threads": 10,
  "timeout": 5,
  "follow_redirects": true,
  "recursive": false,
  "depth": 1,
  "extensions": [],
  "status_codes": [200, 301, 302, 403],
  "exclude_status": [],
  "user_agent": "PathCrawler/1.0",
  "headers": {},
  "log_level": "INFO",
  "delay": 0.0
}
```

## Output Examples

Console output resembles:

```text
PathCrawler v1.0.0

Target       : http://127.0.0.1:8000/
Wordlist     : wordlists/common.txt
Threads      : 10
Timeout      : 5s

---
[200] /admin                            214 B   0.01s FOUND
[200] /login                            214 B   0.01s FOUND
[200] /secret.txt                        58 B   0.01s FOUND
---
Requests    : 48
Found       : 3
Errors      : 0
Timeouts    : 0
Duration    : 0.30s
```

JSON reports include scan metadata, statistics, wordlist statistics, and structured result objects. CSV reports include path, URL, status code, content length, content type, redirect target, response time, classification, and error columns.

## False-Positive Detection

Before scanning, PathCrawler requests a random path such as `/pc-nonexistent-a1b2c3d4e5f6g7`. If the target returns a custom 404 page with a normal-looking status such as `200`, the baseline response helps identify later responses with the same status, similar content length, and similar content type. Such results are classified as `LIKELY_FALSE_POSITIVE`.

This technique is useful but not perfect. Dynamic pages, compression, authentication changes, load balancers, and application-specific error pages can still cause missed findings or false positives.

## Recursive Scanning

Recursive scanning is disabled by default. When enabled, PathCrawler recurses only into discovered directory-like paths classified as `FOUND`, `FORBIDDEN`, or `REDIRECT`. It does not recurse into paths whose last segment looks like a file name with an extension. Duplicate paths are skipped, and the maximum depth is validated.

## Error Handling

PathCrawler handles invalid URLs, missing or empty wordlists, malformed configuration, malformed headers, invalid status codes, invalid extensions, DNS failures, connection failures, timeouts, SSL errors, permission errors, and invalid report paths. Normal CLI users receive clear messages instead of raw Python tracebacks. `--log-level DEBUG` records additional debugging detail.

## Testing

Run all tests:

```bash
python -m unittest discover
```

The test suite covers wordlist loading, duplicate removal, comment handling, URL construction, config validation, status filtering, false-positive baseline logic, scanner behavior, and error handling.

## Local Demonstration

Start the demo server from the demo directory:

```bash
cd examples/demo_server
python -m http.server 8000
```

In another terminal, from the project root:

```bash
python main.py scan --url http://127.0.0.1:8000 --wordlist wordlists/common.txt -o reports/demo.json
```

Use localhost only for the included demonstration.

## Limitations

- PathCrawler uses GET requests only.
- It does not authenticate unless the user supplies appropriate authorized headers.
- It does not parse links, JavaScript, or HTML.
- False-positive detection is heuristic.
- Very large scans may still be affected by network limits and server rate controls.
- The project intentionally avoids exploitation features.

## Ethical and Legal Usage

This tool is intended ONLY for authorized security testing. Use it only on systems you own, administer, or have explicit written permission to test. Unauthorized scanning may be illegal and disruptive. PathCrawler is designed for education, defensive validation, and lawful assessments.

## Future Improvements

- Optional HEAD request mode.
- More detailed response fingerprinting.
- Authentication profiles stored outside reports.
- Sitemap export.
- Resume support for interrupted scans.
- Better terminal color support while preserving plain output compatibility.

## Project Structure

```text
PathCrawler/
├── main.py
├── README.md
├── LICENSE
├── requirements.txt
├── config.json
├── pathcrawler/
├── wordlists/
├── reports/
├── tests/
├── docs/
└── examples/
    └── demo_server/
```
