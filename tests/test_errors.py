import unittest
import sys
import os

# Add parent directory to path to import errors module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from errors import (
    GoFileError, 
    ContentNotFoundError, 
    GoFileAPIError, 
    ContentTypeNotSupportedError,
    ServerError
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
        
    def test_gofile_api_error(self):
        """Test GoFileAPIError class"""
        error = GoFileAPIError("API error")
        self.assertEqual(str(error), "GoFile API Error: API error")
        
    def test_content_type_not_supported_error(self):
        """Test ContentTypeNotSupportedError class"""
        error = ContentTypeNotSupportedError("folder")
        self.assertEqual(str(error), "Content type 'folder' is not supported")
        
    def test_server_error(self):
        """Test ServerError class"""
        error = ServerError("Server unavailable")
        self.assertEqual(str(error), "Server Error: Server unavailable")

if __name__ == '__main__':
    unittest.main()
