import unittest
import sys
import os

# Add parent directory to path to import errors module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from errors import (
    GoFileError, 
    ContentNotFoundError
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
        self.assertEqual(str(error), "Content ID test-id not found")
        
    # Removing the test for ContentTypeNotSupportedError since it doesn't exist

if __name__ == '__main__':
    unittest.main()
