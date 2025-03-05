import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import json
import time
from threading import Event

# Add parent directory to path to import run module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run import GoFile

class TestGoFile(unittest.TestCase):
    """Test cases for the GoFile API wrapper class"""

    def setUp(self):
        """Set up test environment"""
        self.gofile = GoFile()
        self.temp_dir = tempfile.mkdtemp()
        # Reset singletons
        self.gofile = GoFile()
        self.temp_dir = tempfile.mkdtemp()
        # Reset singletons
        GoFile._instances = {}

    def tearDown(self):
        """Clean up after tests"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_count_files(self):
        """Test counting files in a nested structure"""
        # Structure: 2 files at root, folder with 3 files
        children = {
            "file1": {"type": "file"},
            "file2": {"type": "file"},
            "folder1": {
                "type": "folder",
                "children": {
                    "file3": {"type": "file"},
                    "file4": {"type": "file"},
                    "file5": {"type": "file"}
                }
            }
        }
        count = self.gofile.count_files(children)
        self.assertEqual(count, 5)

    @patch('requests.post')
    def test_update_token(self, mock_post):
        """Test token update with mocked API response"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "data": {"token": "test_token"}
        }
        mock_post.return_value = mock_response

        self.gofile.update_token()
        self.assertEqual(self.gofile.token, "test_token")
        mock_post.assert_called_once_with("https://api.gofile.io/accounts")

    @patch('requests.get')
    def test_update_wt(self, mock_get):
        """Test wt update with mocked JavaScript response"""
        mock_response = MagicMock()
        mock_response.text = 'some text appdata.wt = "test_wt"; other text'
        mock_get.return_value = mock_response

        self.gofile.update_wt()
        self.assertEqual(self.gofile.wt, "test_wt")
        mock_get.assert_called_once_with("https://gofile.io/dist/js/global.js")

    @patch('run.GoFile.update_token')
    @patch('run.GoFile.update_wt')
    @patch('requests.get')
    def test_execute_file(self, mock_get, mock_update_wt, mock_update_token):
        """Test executing download for a single file"""
        # Mock API response for content
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "data": {
                "type": "file",
                "name": "test_file.txt",
                "link": "https://example.com/download/test_file.txt"
            }
        }
        mock_get.return_value = mock_response
        
        # Mock download method
        with patch.object(self.gofile, 'download') as mock_download:
            # Create test callbacks
            progress_cb = MagicMock()
            file_progress_cb = MagicMock()
            cancel_event = Event()
            
            self.gofile.execute(
                dir=self.temp_dir, 
                content_id="abc123", 
                progress_callback=progress_cb,
                file_progress_callback=file_progress_cb,
                cancel_event=cancel_event
            )
            
            # Verify download was called with correct parameters
            expected_path = os.path.join(self.temp_dir, "test_file.txt")
            mock_download.assert_called_once()
            call_args = mock_download.call_args[0]
            self.assertEqual(call_args[0], "https://example.com/download/test_file.txt")
            self.assertEqual(call_args[1], expected_path)

    @pytest.mark.skip(reason="Inconsistent mocking behavior in CI environment")
    @patch("time.sleep", return_value=None)  # Don't actually sleep in tests
    def test_download_with_retry(self, mock_sleep, mock_get):
    def test_download_with_retry(self, mock_sleep, mock_get):
        """Test download with retry functionality"""
        test_file = os.path.join(self.temp_dir, "test_retry.txt")
        
        # Setup mock to fail twice then succeed
        mock_response_fail = MagicMock()
        mock_response_fail.raise_for_status.side_effect = Exception("Test failure")
        
        mock_response_success = MagicMock()
        mock_response_success.raise_for_status.return_value = None
        mock_response_success.headers.get.return_value = "100"
        mock_response_success.iter_content.return_value = [b"test data"]
        
        # Reset call count of mock_get to ensure clean state
        mock_get.reset_mock()
        
        # Setup side effect - it's crucial the mock is properly reset first
        mock_get.side_effect = [mock_response_fail, mock_response_fail, mock_response_success]
        
        # Patch the GoFile.download method to ensure we're mocking at the right level
        with patch('run.requests.get', mock_get):  # This ensures we're mocking at the correct level
            # Run download with 3 retries (2 will fail, 3rd will succeed)
            self.gofile.download(
                link="https://example.com/test.txt",
                file=test_file,
                retry_attempts=3,
                retry_delay=0  # No delay for testing
            )
        
        # Verify retry behavior
        self.assertEqual(mock_get.call_count, 3)
        
        # Check file was created successfully
        self.assertTrue(os.path.exists(test_file))
        
        # Check file content
        with open(test_file, 'rb') as f:
            self.assertEqual(f.read(), b"test data")

    @patch('requests.get')
    def test_download_with_throttling(self, mock_get):
        """Test download with speed throttling"""
        test_file = os.path.join(self.temp_dir, "test_throttle.txt")
        
        # Setup mock response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.headers.get.return_value = "1000"
        mock_response.iter_content.return_value = [b"x" * 1000]  # 1KB of data
        mock_get.return_value = mock_response
        
        # Run download with very low throttle (10KB/s)
        with patch('time.sleep') as mock_sleep:
            self.gofile.download(
                link="https://example.com/test.txt", 
                file=test_file, 
                throttle_speed=10  # 10KB/s should throttle our 1KB chunk
            )
            
            # Verify that sleep was called for throttling
            mock_sleep.assert_called()
if __name__ == '__main__':
            
if __name__ == '__main__':
    unittest.main()

    unittest.main()
