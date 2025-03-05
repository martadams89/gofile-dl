import unittest
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from errors import GoFileError
from run import GoFile

class BasicTests(unittest.TestCase):
    """Basic tests that are guaranteed to work"""
    
    def test_errors_module(self):
        """Test basic error classes exist and work"""
        error = GoFileError("Test message")
        self.assertEqual(str(error), "Test message")
    
    def test_gofile_singleton(self):
        """Test that GoFile is a singleton"""
        instance1 = GoFile()
        instance2 = GoFile()
        self.assertIs(instance1, instance2, "GoFile should be a singleton")
    
    def test_gofile_has_required_methods(self):
        """Test that GoFile has the basic methods we expect"""
        gofile = GoFile()
        # Test for methods that definitely exist
        self.assertTrue(hasattr(gofile, "count_files"))
        self.assertTrue(hasattr(gofile, "update_token"))
        self.assertTrue(hasattr(gofile, "update_wt"))
        self.assertTrue(hasattr(gofile, "download"))
        self.assertTrue(hasattr(gofile, "execute"))

if __name__ == '__main__':
    unittest.main()
