import contextlib
import http.server
import socketserver
import tempfile
import threading
import time
import unittest
from pathlib import Path

from pathcrawler.models import ScanConfig
from pathcrawler.scanner import PathCrawlerScanner


class DemoHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/admin":
            body = b"admin page"
            self.send_response(200)
        elif self.path == "/login":
            body = b"login page"
            self.send_response(200)
        else:
            body = b"missing"
            self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


class ScannerTests(unittest.TestCase):
    def test_basic_scanner_behavior(self):
        with run_server() as base_url, tempfile.TemporaryDirectory() as directory:
            wordlist = Path(directory) / "words.txt"
            wordlist.write_text("admin\nlogin\nmissing\n", encoding="utf-8")
            config = ScanConfig(
                target_url=base_url,
                wordlist_path=str(wordlist),
                threads=2,
                timeout=2,
                status_codes=[200],
                follow_redirects=False,
            )
            results, stats, word_stats, baseline = PathCrawlerScanner(config).scan()

        paths = {result.path for result in results}
        self.assertIn("/admin", paths)
        self.assertIn("/login", paths)
        self.assertNotIn("/missing", paths)
        self.assertGreaterEqual(stats.requests, 4)
        self.assertEqual(word_stats.loaded, 3)
        self.assertEqual(baseline.status_code, 404)

    def test_timeout_handling(self):
        with run_slow_server() as base_url, tempfile.TemporaryDirectory() as directory:
            wordlist = Path(directory) / "words.txt"
            wordlist.write_text("slow\n", encoding="utf-8")
            config = ScanConfig(
                target_url=base_url,
                wordlist_path=str(wordlist),
                threads=1,
                timeout=0.05,
                status_codes=[200],
            )
            results, stats, _word_stats, _baseline = PathCrawlerScanner(config).scan()

        self.assertEqual(results, [])
        self.assertGreaterEqual(stats.timeouts, 1)


@contextlib.contextmanager
def run_server():
    server = socketserver.TCPServer(("127.0.0.1", 0), DemoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class SlowHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        time.sleep(0.3)
        body = b"slow"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, format, *args):  # noqa: A003
        return


@contextlib.contextmanager
def run_slow_server():
    server = socketserver.TCPServer(("127.0.0.1", 0), SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
