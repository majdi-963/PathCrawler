# Limitations

- PathCrawler only performs HTTP GET requests.
- It does not crawl links from HTML or JavaScript.
- It does not perform exploitation or vulnerability payload testing.
- It does not guess credentials or bypass authentication.
- False-positive detection is heuristic and can be affected by dynamic pages.
- Recursive scanning is intentionally conservative.
- Results depend heavily on wordlist quality.
- Large scans can still be limited by network latency, server rate controls, or authorization boundaries.

These limitations are appropriate for the project's educational and defensive scope.
