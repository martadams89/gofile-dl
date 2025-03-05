import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import time
import re
from threading import Event

# Add parent directory to path to import run module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run import GoFile
from errors import PasswordError, ContentNotFoundError

class TestGoFileExtended(unittest.TestCase):
    """Additional test cases for GoFile class to increase coverage"""

    def setUp(self):
        """Set up test environment"""
        self.gofile = GoFile()
        self.temp_dir = tempfile.mkdtemp()
        # Reset singletons
        GoFile._instances = {}

    def tearDown(self):
        """Clean up after tests"""
        import shutil
        shutil.rmtree(self.temp_dir)
        
    @patch('requests.get')
    def test_content_api_call(self, mock_get):
        """Test the content API call with password"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "data": {
                "contents": {
                    "file1": {"type": "file", "name": "file1.txt", "link": "https://example.com/file1.txt"}
                }
            }
        }
        mock_get.return_value = mock_response
        
        # Set token and wt values
        self.gofile.token = "test-token"
        self.gofile.wt = "test-wt"
        
        # Call the content API
        result = self.gofile.get_content("abc123", password="test-password")
        
        # Verify the API call
        mock_get.assert_called_once()
        self.assertEqual(result["status"], "ok")
        
    @patch('requests.get')
    def test_password_protected_content(self, mock_get):
        """Test handling password-protected content"""
        # First response indicates password required
        mock_response_pwd_needed = MagicMock()
        mock_response_pwd_needed.json.return_value = {
            "status": "error",
            "errorMessage": "Password required"
        }
        
        # Second response with password succeeds
        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {
            "status": "ok",
            "data": {
                "contents": {
                    "file1": {"type": "file", "name": "file1.txt", "link": "https://example.com/file1.txt"}
                }
            }
        }
        
        mock_get.side_effect = [mock_response_pwd_needed, mock_response_success]
        
        # Set token and wt values
        self.gofile.token = "test-token"
        self.gofile.wt = "test-wt"
        
        # Call without password should raise PasswordError
        with self.assertRaises(PasswordError):
            self.gofile.get_content("abc123")
            
        # Call with password should succeed
        result = self.gofile.get_content("abc123", password="correct-password")
        self.assertEqual(result["status"], "ok")
        
    @patch('run.GoFile.get_content')
    @patch('run.GoFile.download')
    def test_execute_folder_traversal(self, mock_download, mock_get_content):
        """Test folder traversal logic in execute method"""
        # Mock folder content structure
        mock_get_content.return_value = {
            "status": "ok",
            "data": {
                "name": "Test Folder",
                "type": "folder",
                "contents": {
                    "file1": {"type": "file", "name": "file1.txt", "link": "https://example.com/file1.txt"},
                    "subfolder": {
                        "type": "folder",
                        "name": "Subfolder",
                        "contents": {
                            "file2": {"type": "file", "name": "file2.txt", "link": "https://example.com/file2.txt"}
                        }
                    }
                }
            }
        }
        
        # Set up test callbacks
        progress_cb = MagicMock()
        file_progress_cb = MagicMock()
        cancel_event = Event()
        name_cb = MagicMock()
        
        # Execute with folder traversal
        self.gofile.execute(
            dir=self.temp_dir,
            content_id="folder123",
            progress_callback=progress_cb,
            file_progress_callback=file_progress_cb,
            name_callback=name_cb,
            cancel_event=cancel_event
        )
        
        # Verify appropriate number of downloads (2 files)
        self.assertEqual(mock_download.call_count, 2)
        
        # Verify name callback was called
        name_cb.assert_called_once_with("Test Folder")
        
    @patch('requests.get')
    def test_download_error_handling(self, mock_get):
        """Test error handling during download"""
        test_file = os.path.join(self.temp_dir, "error_test.txt")
        
        # Mock failed response
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("Network error")
        mock_get.return_value = mock_response
        
        # Attempt download with only 1 retry
        with self.assertRaises(Exception):
            self.gofile.download(
                link="https://example.com/test.txt",
                file=test_file,
                retry_attempts=1
            )
            
        # File should not exist after failed download
        self.assertFalse(os.path.exists(test_file))
        
    def test_singleton_pattern(self):
        """Test the singleton pattern implementation"""
        # Create two instances with identical parameters
        instance1 = GoFile()
        instance2 = GoFile()
        
        # They should be the same object
        self.assertIs(instance1, instance2)
        
        # But different from an instance with different parameters
        instance3 = GoFile(base_url="https://different-url.com")
        self.assertIsNot(instance1, instance3)

    @patch('run.GoFile.extract_content_id')
    def test_url_parsing(self, mock_extract):
        """Test URL parsing functionality"""
        mock_extract.return_value = "abc123"
        
        # Test execute with URL instead of content_id
        with patch.object(self.gofile, 'get_content') as mock_get_content:
            mock_get_content.return_value = {
                "status": "ok",
                "data": {
                    "type": "file",
                    "name": "test_file.txt",
                    "link": "https://example.com/download/test_file.txt"
                }
            }
            
            # Use the mock but also verify it - fixes the linting error
            with patch.object(self.gofile, 'download') as mock_download:
                # Call execute with URL
                self.gofile.execute(
                    dir=self.temp_dir,
                    url="https://gofile.io/d/abc123"
                )
                
                # Verify content_id was extracted and used
                mock_extract.assert_called_with("https://gofile.io/d/abc123")
                mock_get_content.assert_called_with("abc123", None)
                
                # Verify download was called with the right parameters
                mock_download.assert_called_once()
                args = mock_download.call_args[0]
                self.assertEqual(args[0], "https://example.com/download/test_file.txt")

    # Add these new tests to increase coverage

    @patch('run.GoFile.update_token')
    @patch('run.GoFile.update_wt')
    def test_initialization(self, mock_update_wt, mock_update_token):
        """Test GoFile initialization"""
        gofile = GoFile(base_url="https://custom.example.com")
        self.assertEqual(gofile.base_url, "https://custom.example.com")
        mock_update_token.assert_called_once()
        mock_update_wt.assert_called_once()

    @patch('requests.get')
    def test_extract_content_id(self, mock_get):
        """Test extraction of content ID from various URL formats"""
        # Test different URL patterns
        self.assertEqual(self.gofile.extract_content_id("https://gofile.io/d/abc123"), "abc123")
        self.assertEqual(self.gofile.extract_content_id("https://gofile.io/d/abc123/"), "abc123")
        self.assertEqual(self.gofile.extract_content_id("abc123"), "abc123")
        
        # Test invalid URL pattern
        with self.assertRaises(ValueError):
            self.gofile.extract_content_id("")

    @patch('run.GoFile.get_content')
    def test_missing_content(self, mock_get_content):
        """Test handling of missing content"""
        from errors import ContentNotFoundError
        
        # Mock API response for missing content
        mock_get_content.side_effect = ContentNotFoundError("missing-id")
        
        with self.assertRaises(ContentNotFoundError):
            self.gofile.execute(dir=self.temp_dir, content_id="missing-id")

    @patch('run.GoFile.get_content')
    def test_execute_with_callbacks(self, mock_get_content):
        """Test execute method with all callbacks"""
        # Mock content response
        mock_get_content.return_value = {
            "status": "ok",
            "data": {
                "type": "file",
                "name": "test_file.txt",
                "link": "https://example.com/download/test_file.txt"
            }
        }
        
        # Create mock callbacks
        progress_callback = MagicMock()
        file_progress_callback = MagicMock()
        name_callback = MagicMock()
        cancel_callback = MagicMock(return_value=False)
        pause_callback = MagicMock(return_value=False)
        overall_progress_callback = MagicMock()
        
        # Create cancel event that is not set
        cancel_event = Event()
        
        with patch.object(self.gofile, 'download') as mock_download:
            # Execute with all callbacks
            self.gofile.execute(
                dir=self.temp_dir,
                content_id="test123",
                progress_callback=progress_callback,
                file_progress_callback=file_progress_callback,
                name_callback=name_callback,
                cancel_event=cancel_event,
                pause_callback=pause_callback,
                overall_progress_callback=overall_progress_callback,
                start_time=time.time()
            )
            
            # Verify callbacks were used correctly
            name_callback.assert_called_once_with("test_file.txt")
            mock_download.assert_called_once()

    @patch('requests.get')
    def test_cancel_during_download(self, mock_get):
        """Test cancellation during download"""
        test_file = os.path.join(self.temp_dir, "cancel_test.txt")
        
        # Setup mock response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.headers.get.return_value = "1000000"  # 1MB file
        # Return data in chunks to test cancellation mid-download
        mock_response.iter_content.return_value = [b"x" * 1000] * 1000
        mock_get.return_value = mock_response
        
        # Create cancel event that will be set during download
        cancel_event = Event()
        
        # Mock time.sleep to set the cancel event after first chunk
        original_sleep = time.sleep
        
        def mock_sleep_and_cancel(*args, **kwargs):
            cancel_event.set()  # Set cancel event
            return original_sleep(0)  # Don't actually sleep
        
        with patch('time.sleep', side_effect=mock_sleep_and_cancel):
            # Start download that will be cancelled
            self.gofile.download(
                link="https://example.com/large_file.txt",
                file=test_file,
                cancel_event=cancel_event
            )
        
        # Verify file was created but not completed (should be partial)
        self.assertTrue(os.path.exists(test_file))
        self.assertLess(os.path.getsize(test_file), 1000000)  # Size should be less than total

    @patch('run.GoFile.get_content')
    def test_pause_during_download(self, mock_get_content):
        """Test pause/resume during download"""
        # Mock content response
        mock_get_content.return_value = {
            "status": "ok",
            "data": {
                "type": "file",
                "name": "test_file.txt",
                "link": "https://example.com/download/test_file.txt"
            }
        }
        
        # Create a pause state that toggles
        pause_state = {"is_paused": False, "toggle_count": 0}
        
        def toggle_pause():
            pause_state["toggle_count"] += 1
            # Pause on first call, unpause on second call
            pause_state["is_paused"] = pause_state["toggle_count"] % 2 == 1
            return pause_state["is_paused"]
        
        with patch.object(self.gofile, 'download') as mock_download:
            # Execute with pause callback
            self.gofile.execute(
                dir=self.temp_dir,
                content_id="test123",
                pause_callback=toggle_pause
            )
            
            # Verify download called once
            mock_download.assert_called_once()
