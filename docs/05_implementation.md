# Implementation

The implementation is written in Python 3 and uses only the standard library. The HTTP layer uses `urllib.request` with a custom redirect handler. The scanner uses `concurrent.futures.ThreadPoolExecutor` to limit concurrency to a validated thread count between 1 and 100.

The wordlist engine reads UTF-8 input, ignores empty lines and comments, removes duplicates, and returns statistics. Path generation normalizes entries such as `admin`, `/admin`, and `admin/` into consistent absolute paths. Optional extensions generate candidates such as `/admin.php` and `/admin.html`.

Before scanning, the scanner requests a random likely-nonexistent path. The analyzer compares later responses against this baseline to identify likely custom 404 behavior. The algorithm compares status code, content type, and content length tolerance. It is intentionally documented as a heuristic rather than a perfect detector.

The CLI avoids exposing Python tracebacks during normal use. Clear errors are raised for invalid URLs, wordlists, configuration, headers, status codes, extensions, report paths, timeouts, and connection failures.
