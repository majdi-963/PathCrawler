import tempfile
import unittest
from pathlib import Path

from pathcrawler.errors import WordlistError
from pathcrawler.wordlist import generate_paths, load_wordlist


class WordlistTests(unittest.TestCase):
    def test_load_wordlist_ignores_comments_blanks_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "words.txt"
            path.write_text("admin\n\n# comment\n login \nadmin\n", encoding="utf-8")

            entries, stats = load_wordlist(str(path))

        self.assertEqual(entries, ["admin", "login"])
        self.assertEqual(stats.loaded, 2)
        self.assertEqual(stats.comments, 1)
        self.assertEqual(stats.empty, 1)
        self.assertEqual(stats.duplicates, 1)

    def test_missing_wordlist_raises_clear_error(self):
        with self.assertRaises(WordlistError):
            load_wordlist("missing-wordlist.txt")

    def test_generate_paths_with_extensions(self):
        paths = generate_paths(["/admin/", "admin", "robots.txt"], ["php", "html"])
        self.assertEqual(paths, ["/admin", "/admin.php", "/admin.html", "/robots.txt"])

    def test_generate_paths_with_prefix(self):
        paths = generate_paths(["login"], [], "/admin")
        self.assertEqual(paths, ["/admin/login"])


if __name__ == "__main__":
    unittest.main()
