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

class ErrorsTest(unittest.TestCase):
    """Test cases for custom error classes"""

    def test_gofile_error(self):
        """Test the base GoFileError class"""
        error = GoFileError("Test error message")
        self.assertEqual(str(error), "Test error message")
        
    def test_content_not_found_error(self):
        """Test ContentNotFoundError class"""
        error = ContentNotFoundError("test-id")
        # ContentNotFoundError just passes the content ID as the message
        self.assertEqual(str(error), "test-id")
        
    def test_authentication_error(self):
        """Test AuthenticationError class"""
        error = AuthenticationError("Invalid credentials")
        self.assertEqual(str(error), "Invalid credentials")
        
    def test_password_error(self):
        """Test PasswordError class"""
        error = PasswordError("Invalid password")
        self.assertEqual(str(error), "Invalid password")
        
    def test_download_error(self):
        """Test DownloadError class with filename and URL"""
        error = DownloadError("Failed to download", "test.txt", "https://example.com/test.txt")
        self.assertEqual(str(error), "Failed to download: test.txt (https://example.com/test.txt)")
        self.assertEqual(error.filename, "test.txt")
        self.assertEqual(error.url, "https://example.com/test.txt")
        
    def test_throttle_error(self):
        """Test ThrottleError class"""
        error = ThrottleError("Invalid throttle speed")
        self.assertEqual(str(error), "Invalid throttle speed")
        
    def test_retry_exhausted_error(self):
        """Test RetryExhaustedError class"""
        error = RetryExhaustedError("All retry attempts failed")
        self.assertEqual(str(error), "All retry attempts failed")

if __name__ == '__main__':
    unittest.main()
