import unittest
from unittest.mock import patch, MagicMock
import json
import tempfile
import os
import sys
import time
import base64
import threading
from flask import Flask

# Add parent directory to path to import app module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

class TestFlaskAppExtended(unittest.TestCase):
    """Additional test cases for Flask application to increase coverage"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = app.app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        app.config["auth"]["enabled"] = False
        self.client = self.app.test_client()
        self.original_config = app.config.copy()
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up after tests"""
        app.config = self.original_config
        import shutil
        shutil.rmtree(self.temp_dir)
        app.download_tasks = {}

    def test_get_env_var(self):
        """Test environment variable handling"""
        # Test with default value
        result = app.get_env_var("NON_EXISTENT_VAR", "default_value")
        self.assertEqual(result, "default_value")
        
        # Test with type conversion
        os.environ["TEST_INT_VAR"] = "42"
        result = app.get_env_var("TEST_INT_VAR", 0, type_func=int)
        self.assertEqual(result, 42)
        self.assertIsInstance(result, int)
        
        # Test with invalid type conversion
        os.environ["TEST_INVALID_INT"] = "not_an_int"
        with self.assertRaises(ValueError):
            app.get_env_var("TEST_INVALID_INT", 0, type_func=int)
        
        # Test required variable missing
        with self.assertRaises(ValueError):
            app.get_env_var("REQUIRED_MISSING_VAR", required=True)
            
    def test_index_route(self):
        """Test the index route with GET and POST methods"""
        # Test GET
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        
        # Test POST with valid data
        with patch('app.redirect') as mock_redirect:
            response = self.client.post('/', data={
                'url': 'https://gofile.io/d/test',
                'directory': self.temp_dir,
                'password': 'testpass'
            })
            # Should redirect to start_download
            self.assertEqual(response.status_code, 302)

    def test_cancel_remove_delete_endpoints(self):
        """Test task management endpoints"""
        # Create a test task
        task_id = "test-task"
        cancel_event = threading.Event()
        app.download_tasks[task_id] = {
            'progress': 50,
            'cancel_event': cancel_event,
            'status': 'running',
            'url': 'https://example.com',
            'name': 'Test File',
            'out_path': os.path.join(self.temp_dir, "test_file.txt")
        }
        
        # Create a test file
        with open(os.path.join(self.temp_dir, "test_file.txt"), "w") as f:
            f.write("test data")
        
        # Test cancel endpoint
        response = self.client.post(f'/cancel/{task_id}')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(cancel_event.is_set())
        
        # Test remove endpoint
        response = self.client.post(f'/remove/{task_id}')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(task_id, app.download_tasks)
        
        # Add task back for delete test
        app.download_tasks[task_id] = {
            'progress': 100,
            'status': 'completed',
            'out_path': os.path.join(self.temp_dir, "test_file.txt")
        }
        
        # Test delete endpoint
        response = self.client.post(f'/delete/{task_id}')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "test_file.txt")))
        self.assertNotIn(task_id, app.download_tasks)

    def test_pause_endpoint(self):
        """Test pause/resume functionality"""
        task_id = "pause-task"
        app.download_tasks[task_id] = {
            'progress': 50,
            'status': 'running',
            'paused': False
        }
        
        # Test pause
        response = self.client.post(f'/pause/{task_id}')
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(app.download_tasks[task_id]['paused'])
        self.assertEqual(data['status'], 'paused')
        
        # Test resume (toggle pause)
        response = self.client.post(f'/pause/{task_id}')
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(app.download_tasks[task_id]['paused'])
        self.assertEqual(data['status'], 'running')

    @patch('app.GoFile')
    @patch('app.threading.Thread')
    def test_download_task_function(self, mock_thread, mock_gofile_class):
        """Test the download_task background function"""
        # Setup mock objects
        mock_gofile = MagicMock()
        mock_gofile_class.return_value = mock_gofile
        mock_gofile.execute = MagicMock()
        
        # Create test task
        task_id = "download-test"
        app.download_tasks[task_id] = {
            'progress': 0,
            'cancel_event': threading.Event(),
            'thread': None,
            'status': "running",
            'url': "https://gofile.io/d/test",
            'directory': self.temp_dir,
            'timestamp': time.time(),
            'name': "test_file",
            'paused': False,
            'throttle': 100,
            'retries': 3,
            'files': []
        }
        
        # Run the background task directly
        app.download_task(
            url="https://gofile.io/d/test",
            directory=self.temp_dir,
            password="test-pass",
            task_id=task_id
        )
        
        # Verify GoFile.execute was called with expected args
        mock_gofile.execute.assert_called_once()
        # Check task status updated to completed
        self.assertEqual(app.download_tasks[task_id]['status'], "completed")
        self.assertEqual(app.download_tasks[task_id]['progress'], 100)
        
    def test_browse_endpoint(self):
        """Test the browse endpoint for directory listing"""
        # Create test directory structure
        test_subdir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(test_subdir)
        
        with patch.dict(os.environ, {"BASE_DIR": self.temp_dir}):
            # Test root path
            response = self.client.get('/browse?path=')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIn("directories", data)
            self.assertIn("subdir", data["directories"])
            
            # Test invalid path
            response = self.client.get('/browse?path=nonexistent')
            self.assertEqual(response.status_code, 400)
            
    def test_error_handling(self):
        """Test error handling in API endpoints"""
        # Test invalid task ID in progress endpoint
        response = self.client.get('/progress/nonexistent-task')
        self.assertEqual(response.status_code, 404)
        
        # Test start with missing URL
        response = self.client.post('/start', data={})
        self.assertEqual(response.status_code, 400)
        
        # Test delete on non-existent file
        task_id = "nonexistent-file-task"
        app.download_tasks[task_id] = {
            'out_path': "/path/to/nonexistent/file.txt",
            'status': 'completed'
        }
        response = self.client.post(f'/delete/{task_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("already removed", data.get("message"))
