import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
from threading import Event

# Add parent directory to path to import run module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run import GoFile

class RunSimpleTest(unittest.TestCase):
    """Simple tests for the GoFile class to maximize coverage"""
    
    def setUp(self):
        self.gofile = GoFile()
        self.temp_dir = tempfile.mkdtemp()
        # Reset singletons
        GoFile._instances = {}
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('requests.get')
    @patch('requests.post')
    def test_full_execution_flow(self, mock_post, mock_get):
        """Test the complete execution flow with all callbacks"""
        # Mock token update
        mock_post_response = MagicMock()
        mock_post_response.json.return_value = {"status": "ok", "data": {"token": "test_token"}}
        mock_post.return_value = mock_post_response
        
        # Mock wt extraction
        mock_js_response = MagicMock()
        mock_js_response.text = 'appdata.wt = "test_wt";'
        
        # Mock content API response - folder with nested structure
        mock_content_response = MagicMock()
        mock_content_response.json.return_value = {
            "status": "ok",
            "data": {
                "type": "folder",
                "name": "Test Folder",
                "contents": {
                    "file1": {"type": "file", "name": "test1.txt", "link": "https://example.com/1.txt"},
                    "subfolder": {
                        "type": "folder",
                        "name": "Subfolder",
                        "contents": {
                            "file2": {"type": "file", "name": "test2.txt", "link": "https://example.com/2.txt"}
                        }
                    }
                }
            }
        }
        
        # Mock download file response
        mock_download_response = MagicMock()
        mock_download_response.raise_for_status.return_value = None
        mock_download_response.headers.get.return_value = "100"
        mock_download_response.iter_content.return_value = [b"test data"]
        
        # Sequence of responses
        mock_get.side_effect = [
            mock_js_response,     # wt extraction
            mock_content_response, # content API call
            mock_download_response, # first download
            mock_download_response  # second download
        ]
        
        # Create all callbacks
        progress_callback = MagicMock()
        file_progress = MagicMock()
        name_callback = MagicMock()
        pause_callback = MagicMock(return_value=False)
        cancel_event = Event()
        
        # Execute the download
        self.gofile.execute(
            dir=self.temp_dir,
            content_id="abc123",
            progress_callback=progress_callback,
            file_progress_callback=file_progress,
            name_callback=name_callback,
            cancel_event=cancel_event,
            pause_callback=pause_callback,
            password="test_pass",
            throttle_speed=100,
            retry_attempts=3,
            retry_delay=0
        )
        
        # Verify callbacks were called
        self.assertTrue(progress_callback.called)
        self.assertTrue(file_progress.called)
        name_callback.assert_called_with("Test Folder")
        
        # Verify files created
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "Test Folder")))
    
    @patch('requests.get')
    def test_extract_content_id(self, mock_get):
        """Test URL extraction methods"""
        # Different URL formats
        self.assertEqual(self.gofile.extract_content_id("https://gofile.io/d/abc123"), "abc123")
        self.assertEqual(self.gofile.extract_content_id("https://gofile.io/d/abc123/"), "abc123")
        self.assertEqual(self.gofile.extract_content_id("gofile.io/d/abc123"), "abc123")
        self.assertEqual(self.gofile.extract_content_id("abc123"), "abc123")
        
        # Invalid URL
        with self.assertRaises(ValueError):
            self.gofile.extract_content_id("")
