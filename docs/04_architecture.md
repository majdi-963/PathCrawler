# Architecture

PathCrawler uses a modular architecture with clear responsibility boundaries.

- `main.py` starts the CLI.
- `pathcrawler/cli.py` defines argparse commands, help text, and user-facing error handling.
- `pathcrawler/config.py` loads JSON configuration, merges command-line overrides, and validates values.
- `pathcrawler/wordlist.py` loads wordlists and generates normalized paths.
- `pathcrawler/http_client.py` performs HTTP GET requests using `urllib.request`.
- `pathcrawler/analyzer.py` classifies responses and applies false-positive detection.
- `pathcrawler/scanner.py` coordinates baseline requests, concurrency, recursion, and statistics.
- `pathcrawler/reporter.py` prints console output and writes JSON or CSV files.
- `pathcrawler/models.py` contains dataclasses shared by the modules.

This separation makes the code easier to test and explain. For example, URL construction can be tested independently from HTTP networking, and configuration validation can be tested without starting a server.
