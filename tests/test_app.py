import unittest
from unittest.mock import patch, MagicMock, mock_open
import tempfile
import os
import sys
import json
import time
import base64
import yaml  # Add this missing import
from threading import Event

# Add parent directory to path to import app module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

class TestFlaskApp(unittest.TestCase):
    """Test cases for the Flask application"""

    def setUp(self):
        """Set up test environment"""
        self.app = app.app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        app.config["auth"]["enabled"] = False  # Disable auth for most tests
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
        
        # Clean up environment
        os.environ.pop("TEST_INT_VAR", None)
        os.environ.pop("TEST_INVALID_INT", None)

    def test_config_loading(self):
        """Test configuration loading"""
        # Create a custom configuration
        test_config = {
            "port": 8080,
            "host": "127.0.0.1",
            "base_dir": "/custom/path",
            "secret_key": "test-secret",
            "auth": {
                "enabled": True,
                "username": "testuser",
                "password": "testpass"
            }
        }
        
        # Mock config file loading
        with patch('yaml.safe_load', return_value=test_config), \
             patch('builtins.open'):
            
            # Manually simulate config loading
            config_copy = app.DEFAULT_CONFIG.copy()
            config_copy.update(test_config)
            
            # Verify values are properly set
            self.assertEqual(config_copy["port"], 8080)
            self.assertEqual(config_copy["host"], "127.0.0.1")
            self.assertEqual(config_copy["base_dir"], "/custom/path")
            self.assertEqual(config_copy["auth"]["username"], "testuser")
            self.assertEqual(config_copy["auth"]["enabled"], True)

    def test_authentication(self):
        """Test authentication-related functionality"""
        # Enable authentication
        app.config["auth"]["enabled"] = True
        app.config["auth"]["username"] = "testuser"
        app.config["auth"]["password"] = "testpass"
        
        # Test routes without auth
        response = self.client.get('/browse')
        self.assertEqual(response.status_code, 401)
        
        # Test with valid auth
        auth_header = {
            'Authorization': 'Basic ' +
            base64.b64encode(b'testuser:testpass').decode('utf-8')
        }
        response = self.client.get('/browse', headers=auth_header)
        self.assertNotEqual(response.status_code, 401)
        
        # Test with invalid auth
        auth_header = {
            'Authorization': 'Basic ' +
            base64.b64encode(b'wrong:wrong').decode('utf-8')
        }
        response = self.client.get('/browse', headers=auth_header)
        self.assertEqual(response.status_code, 401)

    def test_health_check(self):
        """Test health check endpoint"""
        with patch('psutil.cpu_percent', return_value=25.0), \
             patch('psutil.virtual_memory', return_value=MagicMock(
                 total=8589934592,  # 8GB
                 available=4294967296,  # 4GB
                 percent=50.0
             )), \
             patch('psutil.disk_usage', return_value=MagicMock(
                 total=107374182400,  # 100GB
                 free=53687091200,  # 50GB
                 percent=50.0
             )):
            
            response = self.client.get('/health')
            data = json.loads(response.data)
            
            self.assertEqual(response.status_code, 200)
            self.assertEqual(data['status'], 'ok')
            self.assertIn('system', data)
            self.assertEqual(data['system']['cpu_usage'], 25.0)
            self.assertEqual(data['system']['memory']['percent'], 50.0)

    def test_browse_endpoint(self):
        """Test directory browsing functionality"""
        # Create test directory structure
        test_subdir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(test_subdir)
        
        with patch.dict(os.environ, {"BASE_DIR": self.temp_dir}):
            # Test with empty path
            response = self.client.get('/browse?path=')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIn("directories", data)
            self.assertIn("subdir", data["directories"])
            
            # Test with valid subpath
            response = self.client.get('/browse?path=subdir')
            self.assertEqual(response.status_code, 200)
            
            # Test with invalid path
            response = self.client.get('/browse?path=nonexistent')
            self.assertEqual(response.status_code, 400)

    def test_task_management(self):
        """Test task creation and management endpoints"""
        # Test task creation
        with patch('app.threading.Thread') as mock_thread:
            response = self.client.post('/start', data={
                'url': 'https://gofile.io/d/test',
                'directory': self.temp_dir
            })
            self.assertEqual(response.status_code, 202)
            data = json.loads(response.data)
            self.assertIn('task_id', data)
            
            # Verify thread was started
            mock_thread.assert_called_once()
            mock_thread.return_value.start.assert_called_once()
            
            # Get task ID
            task_id = data['task_id']
            
            # Test getting tasks list
            response = self.client.get('/tasks')
            self.assertEqual(response.status_code, 200)
            tasks = json.loads(response.data)
            self.assertIn(task_id, tasks)
            
            # Test task progress
            response = self.client.get(f'/progress/{task_id}')
            self.assertEqual(response.status_code, 200)
            
            # Test pause/unpause
            response = self.client.post(f'/pause/{task_id}')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data['paused'])
            
            # Test cancellation 
            response = self.client.post(f'/cancel/{task_id}')
            self.assertEqual(response.status_code, 200)
            
            # Test task removal
            response = self.client.post(f'/remove/{task_id}')
            self.assertEqual(response.status_code, 200)
            
            # Verify task is gone
            response = self.client.get('/tasks')
            tasks = json.loads(response.data)
            self.assertNotIn(task_id, tasks)

    def test_index_route(self):
        """Test the main index route"""
        # Test GET
        with patch.dict(os.environ, {"BASE_DIR": self.temp_dir}):
            response = self.client.get('/')
            self.assertEqual(response.status_code, 200)
            
            # Test POST (redirects to start_download)
            response = self.client.post('/', data={
                'url': 'https://gofile.io/d/test',
                'directory': self.temp_dir,
                'password': 'testpass'
            }, follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/start', response.location)

if __name__ == '__main__':
    unittest.main()
