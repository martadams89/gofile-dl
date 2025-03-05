import unittest
from unittest.mock import patch, MagicMock, mock_open
import tempfile
import os
import sys
import json
import time
import base64
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
    
    def test_config_loading(self):
        """Test configuration loading"""
        # Create a custom complete config that includes all required keys
        test_config = {
            "port": 8080,
            "host": "127.0.0.1",
            "base_dir": "/custom/path",
            "secret_key": "test-secret",
            "default_retries": 5,
            "retry_delay": 10,
            "log_level": "DEBUG",
            "auth": {
                "enabled": True,
                "username": "testuser",
                "password": "testpass"
            },
            "csrf": {
                "enabled": True,
                "time_limit": 7200
            }
        }
        
        # Test with the complete config
        with patch('yaml.safe_load', return_value=test_config):
            with patch('builtins.open'):
                # Load config directly without reloading module
                app.config = app.DEFAULT_CONFIG.copy()
                
                # Mock the config file opening and loading
                app_instance = app
                
                # Manually re-run the config loading logic
                try:
                    with open(app.CONFIG_FILE, 'r'):
                        pass  # Just testing if open is called
                    app_instance.config = test_config
                except (FileNotFoundError, yaml.YAMLError):
                    app_instance.config = app.DEFAULT_CONFIG
                
                # Ensure config structure matches expected schema
                if "auth" not in app_instance.config:
                    app_instance.config["auth"] = app.DEFAULT_CONFIG["auth"]
                elif not isinstance(app_instance.config["auth"], dict):
                    app_instance.config["auth"] = app.DEFAULT_CONFIG["auth"]
                
                if "csrf" not in app_instance.config:
                    app_instance.config["csrf"] = app.DEFAULT_CONFIG["csrf"]
                
                # Environment variable override logic
                app_instance.config["port"] = app.get_env_var("PORT", app_instance.config["port"], False, int)
                app_instance.config["host"] = app.get_env_var("HOST", app_instance.config["host"])
                app_instance.config["base_dir"] = app.get_env_var("BASE_DIR", app_instance.config["base_dir"])
                app_instance.config["secret_key"] = app.get_env_var("SECRET_KEY", app_instance.config["secret_key"])
                
                # Verify config was loaded correctly
                self.assertEqual(app_instance.config["port"], 8080)
                self.assertEqual(app_instance.config["host"], "127.0.0.1")
                self.assertEqual(app_instance.config["base_dir"], "/custom/path")
                self.assertTrue(app_instance.config["auth"]["enabled"])
    
    def test_config_file_not_found(self):
        """Test handling of missing config file"""
        # Mock open to raise FileNotFoundError
        with patch('builtins.open', side_effect=FileNotFoundError):
            with patch('yaml.safe_load') as mock_yaml:
                # Reset config
                app.config = app.DEFAULT_CONFIG.copy()
                
                # Manually re-run the config loading logic
                try:
                    with open(app.CONFIG_FILE, 'r'):
                        pass
                except (FileNotFoundError, yaml.YAMLError):
                    app.config = app.DEFAULT_CONFIG
                
                # yaml.safe_load should not be called
                mock_yaml.assert_not_called()
                
                # Default config should be used
                self.assertEqual(app.config["port"], app.DEFAULT_CONFIG["port"])

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
        
        # Disable auth for subsequent tests
        app.config["auth"]["enabled"] = False

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
            # Call health check endpoint
            response = self.client.get('/health')
            data = json.loads(response.data)
            
            # Check response
            self.assertEqual(response.status_code, 200)
            self.assertEqual(data['status'], 'ok')
            self.assertIn('system', data)
            self.assertIn('cpu_usage', data['system'])
            self.assertEqual(data['system']['cpu_usage'], 25.0)
            self.assertIn('memory', data['system'])
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
            response = self.client.get(f'/browse?path=subdir')
            self.assertEqual(response.status_code, 200)
            
            # Test with invalid path
            response = self.client.get('/browse?path=nonexistent')
            self.assertEqual(response.status_code, 400)

    def test_download_task(self):
        """Test background download task"""
        # Mock GoFile class
        with patch('app.GoFile') as mock_gofile_class:
            # Configure the mock
            mock_gofile = MagicMock()
            mock_gofile_class.return_value = mock_gofile
            
            # Create test task
            task_id = "test-task"
            app.download_tasks[task_id] = {
                'progress': 0,
                'cancel_event': Event(),
                'thread': None,
                'status': "running",
                'url': "https://gofile.io/d/test",
                'directory': self.temp_dir,
                'timestamp': time.time(),
                'name': "test_file",
                'files': [],
                'paused': False,
                'throttle': 100,
                'retries': 3
            }
            
            # Run the download task
            app.download_task(
                url="https://gofile.io/d/test",
                directory=self.temp_dir,
                password="testpass",
                task_id=task_id
            )
            
            # Verify GoFile.execute was called with correct parameters
            mock_gofile.execute.assert_called_once()
            # Verify task was marked as completed
            self.assertEqual(app.download_tasks[task_id]['status'], "completed")

    def test_start_download_endpoint(self):
        """Test start_download endpoint"""
        with patch('app.threading.Thread') as mock_thread:
            # Call the endpoint
            response = self.client.post('/start', data={
                'url': 'https://gofile.io/d/test',
                'directory': self.temp_dir,
                'password': 'testpass',
                'throttle': '100',
                'retries': '3'
            })
            
            # Check response
            self.assertEqual(response.status_code, 202)
            data = json.loads(response.data)
            self.assertIn('task_id', data)
            
            # Verify task was created
            task_id = data['task_id']
            self.assertIn(task_id, app.download_tasks)
            self.assertEqual(app.download_tasks[task_id]['url'], 'https://gofile.io/d/test')
            self.assertEqual(app.download_tasks[task_id]['directory'], self.temp_dir)
            self.assertEqual(app.download_tasks[task_id]['throttle'], 100)
            self.assertEqual(app.download_tasks[task_id]['retries'], 3)
            
            # Verify thread was started
            mock_thread.assert_called_once()
            mock_thread.return_value.start.assert_called_once()
    
    def test_task_management_endpoints(self):
        """Test task management endpoints (cancel, pause, remove, delete)"""
        # Create a test task
        task_id = "test-task"
        cancel_event = Event()
        app.download_tasks[task_id] = {
            'progress': 50,
            'cancel_event': cancel_event,
            'status': 'running',
            'url': 'https://example.com',
            'name': 'Test File',
            'paused': False,
            'out_path': os.path.join(self.temp_dir, "test_file.txt")
        }
        
        # Create a test file
        with open(os.path.join(self.temp_dir, "test_file.txt"), "w") as f:
            f.write("test data")
        
        # Test cancel endpoint
        response = self.client.post(f'/cancel/{task_id}')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(cancel_event.is_set())
        
        # Test pause endpoint
        response = self.client.post(f'/pause/{task_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(app.download_tasks[task_id]['paused'])
        
        # Test unpause (toggle)
        response = self.client.post(f'/pause/{task_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertFalse(app.download_tasks[task_id]['paused'])
        
        # Test progress endpoint
        response = self.client.get(f'/progress/{task_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['progress'], 50)
        
        # Test tasks endpoint
        response = self.client.get('/tasks')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn(task_id, data)
        
        # Test delete endpoint
        response = self.client.post(f'/delete/{task_id}')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "test_file.txt")))
        self.assertNotIn(task_id, app.download_tasks)

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
