import unittest

from pathcrawler.analyzer import FOUND, LIKELY_FALSE_POSITIVE, NOT_FOUND, ResponseAnalyzer
from pathcrawler.models import HTTPResponse, ScanConfig


class AnalyzerTests(unittest.TestCase):
    def test_false_positive_baseline_logic(self):
        config = ScanConfig(target_url="http://127.0.0.1:8000/", wordlist_path="words.txt")
        baseline = HTTPResponse(
            url="http://127.0.0.1:8000/nope",
            status_code=200,
            content_length=5000,
            content_type="text/html",
        )
        analyzer = ResponseAnalyzer(config, baseline)
        response = HTTPResponse(
            url="http://127.0.0.1:8000/admin",
            status_code=200,
            content_length=5030,
            content_type="text/html; charset=utf-8",
        )

        result = analyzer.analyze("/admin", response)

        self.assertEqual(result.classification, LIKELY_FALSE_POSITIVE)

    def test_distinct_response_remains_found(self):
        config = ScanConfig(target_url="http://127.0.0.1:8000/", wordlist_path="words.txt")
        baseline = HTTPResponse(
            url="http://127.0.0.1:8000/nope",
            status_code=200,
            content_length=5000,
            content_type="text/html",
        )
        analyzer = ResponseAnalyzer(config, baseline)
        response = HTTPResponse(
            url="http://127.0.0.1:8000/admin",
            status_code=200,
            content_length=8420,
            content_type="text/html",
        )

        result = analyzer.analyze("/admin", response)

        self.assertEqual(result.classification, FOUND)

    def test_status_filtering(self):
        config = ScanConfig(
            target_url="http://127.0.0.1:8000/",
            wordlist_path="words.txt",
            status_codes=[200],
            exclude_status=[403],
        )
        analyzer = ResponseAnalyzer(config)
        included = analyzer.analyze(
            "/ok",
            HTTPResponse(url="http://127.0.0.1:8000/ok", status_code=200, content_length=10),
        )
        excluded = analyzer.analyze(
            "/missing",
            HTTPResponse(url="http://127.0.0.1:8000/missing", status_code=404, content_length=10),
        )

        self.assertTrue(analyzer.should_include(included))
        self.assertFalse(analyzer.should_include(excluded))
        self.assertEqual(excluded.classification, NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
