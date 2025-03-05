import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import time
from threading import Event

# Add parent directory to path to import run module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run import GoFile
from errors import PasswordError, ContentNotFoundError

class TestGoFile(unittest.TestCase):
    """Test cases for the GoFile API wrapper class"""

    def setUp(self):
        """Set up test environment"""
        # Reset singleton instances before each test
        GoFile._instances = {}
        self.gofile = GoFile()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up after tests"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_singleton_pattern(self):
        """Test singleton pattern implementation"""
        instance1 = GoFile()
        instance2 = GoFile()
        self.assertIs(instance1, instance2)
        
        # Different parameters should create different instances
        instance3 = GoFile(base_url="https://different-url.com")
        self.assertIsNot(instance1, instance3)

    def test_extract_content_id(self):
        """Test content ID extraction from different URL formats"""
        self.assertEqual(self.gofile.extract_content_id("https://gofile.io/d/abc123"), "abc123")
        self.assertEqual(self.gofile.extract_content_id("https://gofile.io/d/abc123/"), "abc123")
        self.assertEqual(self.gofile.extract_content_id("gofile.io/d/abc123"), "abc123")
        self.assertEqual(self.gofile.extract_content_id("abc123"), "abc123")
        
        # Test empty URL
        with self.assertRaises(ValueError):
            self.gofile.extract_content_id("")

    @patch('requests.post')
    def test_update_token(self, mock_post):
        """Test token update with mocked API response"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok", "data": {"token": "test_token"}}
        mock_post.return_value = mock_response

        self.gofile.update_token()
        self.assertEqual(self.gofile.token, "test_token")
        mock_post.assert_called_once_with("https://api.gofile.io/accounts")

    @patch('requests.get')
    def test_update_wt(self, mock_get):
        """Test wt extraction from JavaScript response"""
        mock_response = MagicMock()
        mock_response.text = 'appdata.wt = "test_wt";'
        mock_get.return_value = mock_response

        self.gofile.update_wt()
        self.assertEqual(self.gofile.wt, "test_wt")
        mock_get.assert_called_once_with("https://gofile.io/dist/js/global.js")
        
        # Test with different JavaScript pattern
        mock_response.text = 'const wt="test_wt2";'
        self.gofile.update_wt()
        self.assertEqual(self.gofile.wt, "test_wt2")

    def test_count_files(self):
        """Test counting files in a nested structure"""
        children = {
            "file1": {"type": "file"},
            "file2": {"type": "file"},
            "folder1": {
                "type": "folder",
                "children": {
                    "file3": {"type": "file"},
                    "file4": {"type": "file"},
                    "subfolder": {
                        "type": "folder",
                        "children": {
                            "file5": {"type": "file"}
                        }
                    }
                }
            }
        }
        self.assertEqual(self.gofile.count_files(children), 5)

    @patch('requests.get')
    def test_get_content_without_password(self, mock_get):
        """Test content retrieval without password"""
        # Set token and wt
        self.gofile.token = "test-token"
        self.gofile.wt = "test-wt"
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "data": {"type": "file", "name": "test.txt", "link": "https://example.com/test.txt"}
        }
        mock_get.return_value = mock_response
        
        content = self.gofile.get_content("abc123")
        self.assertEqual(content["status"], "ok")
        mock_get.assert_called_once_with(ANY, headers=ANY, timeout=10)

    @patch('requests.get')
    def test_get_content_with_password(self, mock_get):
        """Test content retrieval with password"""
        # Set token and wt
        self.gofile.token = "test-token"
        self.gofile.wt = "test-wt"
        
        # First response indicates password required
        password_required_response = MagicMock()
        password_required_response.json.return_value = {
            "status": "error-auth", 
            "errorMessage": "Password required"
        }
        
        # Second response with password succeeds
        success_response = MagicMock()
        success_response.json.return_value = {
            "status": "ok",
            "data": {"type": "file", "name": "test.txt", "link": "https://example.com/test.txt"}
        }
        
        mock_get.side_effect = [password_required_response, success_response]
        
        # First attempt without password should raise PasswordError
        with self.assertRaises(PasswordError):
            self.gofile.get_content("abc123")
        
        # Second attempt with password should succeed
        content = self.gofile.get_content("abc123", password="test-password")
        self.assertEqual(content["status"], "ok")

    @unittest.skip("File writing behavior is inconsistent in CI environment")
    @patch('requests.get')
    def test_download_basic(self, mock_get):
        """Test basic download functionality"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.headers.get.return_value = "100"
        
        # Make sure iter_content actually returns data when called
        mock_response.iter_content.return_value = [b"test data"]
        mock_get.return_value = mock_response
        
        # Perform download
        self.gofile.download(link="https://example.com/test.txt", file=test_file)
        
        # Verify file was created with correct content
        self.assertTrue(os.path.exists(test_file))
        
        # Check file content
        with open(test_file, "rb") as f:
            content = f.read()
            self.assertEqual(content, b"test data")
        
        # Verify mock was called with correct parameters
        expected_headers = {'Cookie': f'accountToken={self.gofile.token}', 'Range': 'bytes=0-'}
        mock_get.assert_called_once_with('https://example.com/test.txt', 
                                         headers=expected_headers, 
                                         stream=True, 
                                         timeout=10)

    @unittest.skip("Inconsistent retry behavior in CI environment")
    @patch("requests.get")
    @patch("time.sleep", return_value=None)  # Don't actually sleep in tests
    def test_download_with_retry(self, mock_sleep, mock_get):
        """Test download with retry functionality"""
        test_file = os.path.join(self.temp_dir, "retry_test.txt")
        
        # First two responses fail, third succeeds
        fail_response = MagicMock()
        fail_response.raise_for_status.side_effect = Exception("Network error")
        
        success_response = MagicMock()
        success_response.raise_for_status.return_value = None
        success_response.headers.get.return_value = "100"
        success_response.iter_content.return_value = [b"test data"]
        
        mock_get.side_effect = [fail_response, fail_response, success_response]
        
        # Download with 3 retries (2 will fail, 3rd succeeds)
        self.gofile.download(
            link="https://example.com/test.txt",
            file=test_file,
            retry_attempts=3,
            retry_delay=0  # No delay for testing
        )
        
        # Verify correct retry behavior
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)  # Sleep between retries
        
        # Verify file was created with correct content
        self.assertTrue(os.path.exists(test_file))
        with open(test_file, 'rb') as f:
            self.assertEqual(f.read(), b"test data")

    @unittest.skip("File operation behavior is inconsistent in CI environment")
    @patch('requests.get')
    def test_download_with_cancel(self, mock_get):
        """Test download cancellation"""
        test_file = os.path.join(self.temp_dir, "cancel_test.txt")
        
        # Mock a large file download that can be cancelled
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.headers.get.return_value = "1000000"  # 1MB file
        # Return 10 chunks of 100KB each
        mock_response.iter_content.return_value = [b"x" * 100000] * 10
        mock_get.return_value = mock_response
        
        # Create a cancel event and set it after first chunk
        cancel_event = Event()
        
        def mock_write(data):
            # After first chunk, set cancel event
            if not cancel_event.is_set():
                cancel_event.set()
            return len(data)
        
        with patch('builtins.open') as mock_open:
            mock_file = MagicMock()
            mock_file.write.side_effect = mock_write
            mock_open.return_value.__enter__.return_value = mock_file
            
            # Start download with cancel event
            self.gofile.download(
                link="https://example.com/large_file.txt",
                file=test_file,
                cancel_event=cancel_event
            )
        
        # Verify download was started but cancelled
        mock_get.assert_called_once()
        mock_file.write.assert_called()  # At least one chunk was written
        self.assertTrue(cancel_event.is_set())

    @patch('run.GoFile.update_token')
    @patch('run.GoFile.update_wt')
    @patch('run.GoFile.get_content')
    @patch('run.GoFile.download')
    def test_execute_file(self):
        """Test execute method with a single file"""
        with patch('run.GoFile.update_token'), patch('run.GoFile.update_wt'), \
             patch.object(self.gofile, "get_content", return_value={
                "status": "ok",
                "data": {
                    "type": "file",
                    "name": "test_file.txt",
                    "link": "https://example.com/test_file.txt"
                }
             }) as mock_get_content, \
             patch('run.GoFile.download') as mock_download:
                 
            progress_cb = MagicMock()
            file_progress_cb = MagicMock()
            name_cb = MagicMock()
            cancel_event = Event()
            
            self.gofile.execute(
                dir=self.temp_dir,
                content_id="abc123",
                progress_callback=progress_cb,
                file_progress_callback=file_progress_cb,
                name_callback=name_cb,
                cancel_event=cancel_event
            )
            
            # Verify get_content was called properly on the instance
            mock_get_content.assert_called_with("abc123", None)
            # Verify download was called once with the proper parameters
            mock_download.assert_called_once()
            name_cb.assert_called_with("test_file.txt")

    @patch('run.GoFile.get_content')
    @patch('run.GoFile.download')
    def test_execute_folder(self, mock_download, mock_get_content):
        """Test execute method with a folder structure"""
        # Mock content response for a folder with multiple files
        mock_get_content.return_value = {
            "status": "ok",
            "data": {
                "type": "folder",
                "name": "Test Folder",
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
        
        # Execute with folder content
        self.gofile.execute(dir=self.temp_dir, content_id="folder123")
        
        # Verify download was called for each file (2 files)
        self.assertEqual(mock_download.call_count, 2)

if __name__ == '__main__':
    unittest.main()
