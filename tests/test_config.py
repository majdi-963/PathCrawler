import tempfile
import unittest
from pathlib import Path

from pathcrawler.config import build_scan_config, load_config_file, parse_header_arguments
from pathcrawler.errors import ConfigurationError
from pathcrawler.http_client import build_url


class ConfigTests(unittest.TestCase):
    def test_build_url_with_base_path(self):
        url = build_url("http://example.test/base/", "/admin")
        self.assertEqual(url, "http://example.test/base/admin")

    def test_build_url_preserves_query(self):
        url = build_url("http://example.test/app?token=demo", "login")
        self.assertEqual(url, "http://example.test/app/login?token=demo")

    def test_valid_config_file_and_cli_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"threads": 3, "timeout": 2}', encoding="utf-8")
            loaded = load_config_file(str(path))
            config = build_scan_config(
                {
                    "target_url": "http://127.0.0.1:8000",
                    "wordlist_path": "wordlists/common.txt",
                    "threads": 7,
                },
                loaded,
            )

        self.assertEqual(config.threads, 7)
        self.assertEqual(config.timeout, 2)

    def test_malformed_config_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{not json}", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_config_file(str(path))

    def test_invalid_thread_count_raises(self):
        with self.assertRaises(ConfigurationError):
            build_scan_config(
                {
                    "target_url": "http://127.0.0.1:8000",
                    "wordlist_path": "words.txt",
                    "threads": 0,
                },
                {},
            )

    def test_malformed_header_raises(self):
        with self.assertRaises(ConfigurationError):
            parse_header_arguments(["BrokenHeader"])


if __name__ == "__main__":
    unittest.main()
