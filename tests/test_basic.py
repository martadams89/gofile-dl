import unittest
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from errors import GoFileError
from run import GoFile, generate_website_token

class BasicTests(unittest.TestCase):
    """Basic tests that are guaranteed to work"""

    def test_errors_module(self):
        """Test basic error classes exist and work"""
        error = GoFileError("Test message")
        self.assertEqual(str(error), "Test message")

    def test_gofile_not_singleton(self):
        """Each GoFile client is independent (avoids token bleed across tasks)."""
        instance1 = GoFile()
        instance2 = GoFile()
        self.assertIsNot(instance1, instance2, "GoFile must not be a process-wide singleton")

    def test_gofile_has_required_methods(self):
        """Test that GoFile has the basic methods we expect"""
        gofile = GoFile()
        for method in ("count_files", "update_token", "website_token",
                       "fetch_contents", "download", "execute", "parse_content_id"):
            self.assertTrue(hasattr(gofile, method), f"missing {method}")

    def test_website_token_is_deterministic_sha256(self):
        """website_token() is a stable 64-hex-char SHA-256 for a fixed window."""
        token = "exampletoken1234567890"
        wt1 = generate_website_token(token, window_offset=0)
        wt2 = generate_website_token(token, window_offset=0)
        self.assertEqual(wt1, wt2)
        self.assertEqual(len(wt1), 64)
        # A different window produces a different token.
        self.assertNotEqual(wt1, generate_website_token(token, window_offset=-1))

    def test_parse_content_id(self):
        """URL parsing accepts share links and bare ids, rejects junk."""
        self.assertEqual(GoFile.parse_content_id("https://gofile.io/d/abc123"), "abc123")
        self.assertEqual(GoFile.parse_content_id("http://www.gofile.io/d/XyZ9/"), "XyZ9")
        self.assertEqual(GoFile.parse_content_id("https://gofile.io/d/abc123?x=1#f"), "abc123")
        self.assertEqual(GoFile.parse_content_id("abc123"), "abc123")
        self.assertIsNone(GoFile.parse_content_id("https://example.com/nope"))

if __name__ == '__main__':
    unittest.main()
