import unittest
import sys
import os

# Add parent directory to path to import errors module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from errors import (
    GoFileError,
    ContentNotFoundError,
    AuthenticationError,
    PasswordError,
    DownloadError,
    ThrottleError,
    RetryExhaustedError
)

class ErrorsSimpleTest(unittest.TestCase):
    """Simple tests for error classes to achieve full coverage"""
    
    def test_all_errors(self):
        """Test all error classes in one test"""
        # Base error
        self.assertEqual(str(GoFileError("Test message")), "Test message")
        
        # Authentication errors
        self.assertEqual(str(AuthenticationError("Auth failed")), "Auth failed")
        self.assertEqual(str(ContentNotFoundError("abc123")), "abc123")
        self.assertEqual(str(PasswordError("Wrong password")), "Wrong password")
        
        # Download related errors
        download_err = DownloadError("Failed", "test.txt", "https://example.com")
        self.assertEqual(download_err.filename, "test.txt")
        self.assertEqual(download_err.url, "https://example.com")
        self.assertEqual(str(download_err), "Failed: test.txt (https://example.com)")
        
        # Other errors
        self.assertEqual(str(ThrottleError("Too fast")), "Too fast")
        self.assertEqual(str(RetryExhaustedError("Too many retries")), "Too many retries")
