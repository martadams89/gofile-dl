import unittest
from unittest.mock import patch, MagicMock
import json
import tempfile
import os
import sys
import base64

# Add parent directory to path to import app module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

class TestFlaskApp(unittest.TestCase):
    """Test cases for Flask application routes and functions"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = app.app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
        
        # Explicitly disable authentication for tests
        app.config["auth"]["enabled"] = False
        
        self.client = self.app.test_client()
        
        # Store original config to restore later
        self.original_config = app.config.copy()
        
        # Create a temporary directory for tests
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up after tests"""
        # Restore original config
        app.config = self.original_config
        
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir)
        
        # Reset tasks
        app.download_tasks = {}
    
    def test_health_check(self):
        """Test the health check endpoint"""
        response = self.client.get('/health')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'ok')
        self.assertIn('system', data)
        self.assertIn('application', data)
    
    def test_tasks_endpoint(self):
        """Test the /tasks endpoint"""
        # Add a mock task
        app.download_tasks = {
            'test-task-1': {
                'progress': 50,
                'status': 'running',
                'url': 'https://example.com',
                'timestamp': 123456789,
                'name': 'Test Task'
            }
        }
        
        response = self.client.get('/tasks')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('test-task-1', data)
        self.assertEqual(data['test-task-1']['progress'], 50)
    
    @patch('app.GoFile')
    @patch('app.threading.Thread')
    def test_start_download(self, mock_thread, mock_gofile):
        """Test the start download endpoint"""
        # Mock thread start method
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        response = self.client.post('/start', data={
            'url': 'https://gofile.io/d/test',
            'directory': self.temp_dir,
            'throttle': '100',
            'retries': '3'
        })
        
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 202)
        self.assertIn('task_id', data)
        self.assertIn(data['task_id'], app.download_tasks)
        mock_thread_instance.start.assert_called_once()
        
        # Verify task configuration
        task = app.download_tasks[data['task_id']]
        self.assertEqual(task['url'], 'https://gofile.io/d/test')
        self.assertEqual(task['directory'], self.temp_dir)
        self.assertEqual(task['throttle'], 100)
        self.assertEqual(task['retries'], 3)
    
    def test_authentication(self):
        """Test authentication when enabled"""
        # Set auth config
        app.config["auth"]["enabled"] = True
        app.config["auth"]["username"] = "testuser"
        app.config["auth"]["password"] = "testpass"
        
        # Test without auth (should fail)
        response = self.client.get('/tasks')
        self.assertEqual(response.status_code, 401)
        
        # Test with invalid auth
        headers = {'Authorization': 'Basic ' + base64.b64encode(b'wrong:wrong').decode('utf-8')}
        response = self.client.get('/tasks', headers=headers)
        self.assertEqual(response.status_code, 401)
        
        # Test with valid auth
        headers = {'Authorization': 'Basic ' + base64.b64encode(b'testuser:testpass').decode('utf-8')}
        response = self.client.get('/tasks', headers=headers)
        self.assertEqual(response.status_code, 200)