import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import tempfile
import os
import sys
import time
import yaml
import shutil
from flask import url_for

# Add parent directory to path to import app module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

class TestFlaskAppComplete(unittest.TestCase):
    """Complete test cases for Flask application with 100% coverage"""
    
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
        shutil.rmtree(self.temp_dir)
        app.download_tasks = {}

    def test_config_loading(self):
        """Test configuration loading from YAML"""
        test_config = {
            "port": 8080,
            "host": "127.0.0.1",
            "auth": {
                "enabled": True,
                "username": "testuser",
                "password": "testpass"
            }
        }
        
        # Mock yaml.safe_load to return our test config
        with patch('yaml.safe_load', return_value=test_config):
            with patch('builtins.open', mock_open()) as mock_file:
                # Reload the app module to trigger config loading
                reload_module = __import__('importlib').reload
                reload_module(app)
                
                # Verify config was loaded correctly
                self.assertEqual(app.config["port"], 8080)
                self.assertEqual(app.config["host"], "127.0.0.1")
                self.assertTrue(app.config["auth"]["enabled"])
                self.assertEqual(app.config["auth"]["username"], "testuser")
                
    def test_config_file_not_found(self):
        """Test handling of missing config file"""
        # Mock open to raise FileNotFoundError
        with patch('builtins.open', side_effect=FileNotFoundError):
            with patch('yaml.safe_load') as mock_yaml:
                # Reload the app module to trigger config loading with error
                reload_module = __import__('importlib').reload
                reload_module(app)
                
                # yaml.safe_load should not be called
                mock_yaml.assert_not_called()
                
                # Default config should be used
                self.assertEqual(app.config["port"], app.DEFAULT_CONFIG["port"])

    def test_auth_required_endpoints(self):
        """Test authentication requirements on protected endpoints"""
        # Enable authentication
        app.config["auth"]["enabled"] = True
        app.config["auth"]["username"] = "testuser"
        app.config["auth"]["password"] = "testpass"
        
        # Test without auth
        response = self.client.get('/browse')
        self.assertEqual(response.status_code, 401)
        
        # Test with auth
        auth_header = {
            'Authorization': 'Basic ' + 
            __import__('base64').b64encode(b'testuser:testpass').decode('utf-8')
        }
        response = self.client.get('/browse', headers=auth_header)
        self.assertEqual(response.status_code, 200)

    @patch('app.psutil.cpu_percent')
    @patch('app.psutil.virtual_memory')
    @patch('app.psutil.disk_usage')
    def test_health_check_detailed(self, mock_disk, mock_memory, mock_cpu):
        """Test detailed health check with system metrics"""
        # Configure mocks
        mock_cpu.return_value = 25.5
        mock_memory.return_value = MagicMock(
            total=8589934592,  # 8GB
            available=4294967296,  # 4GB
            percent=50.0
        )
        mock_disk.return_value = MagicMock(
            total=107374182400,  # 100GB
            free=53687091200,  # 50GB
            percent=50.0
        )
        
        response = self.client.get('/health')
        data = json.loads(response.data)
        
        # Check system info
        self.assertEqual(data['system']['cpu_usage'], 25.5)
        self.assertEqual(data['system']['memory']['percent'], 50.0)
        self.assertEqual(data['system']['memory']['total'], 8589934592)
        self.assertEqual(data['system']['disk']['percent'], 50.0)
        
    @patch('app.psutil.cpu_percent', side_effect=AttributeError)
    def test_health_check_fallback(self, mock_cpu):
        """Test health check fallback when psutil fails"""
        response = self.client.get('/health')
        data = json.loads(response.data)
        
        # Should still return basic info
        self.assertEqual(data['status'], 'ok')
        self.assertIn('system', data)
        self.assertNotIn('cpu_usage', data['system'])
        
    def test_empty_browse_path(self):
        """Test browse endpoint with empty path"""
        with patch.dict(os.environ, {"BASE_DIR": self.temp_dir}):
            # Create a test subdir
            test_subdir = os.path.join(self.temp_dir, "test_dir")
            os.makedirs(test_subdir)
            
            # Test with empty path parameter
            response = self.client.get('/browse?path=')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIn("test_dir", data["directories"])
            
    @patch('app.GoFile.execute', side_effect=Exception("Test error"))
    def test_download_task_exception(self, mock_execute):
        """Test exception handling in download task"""
        # Create a test task
        task_id = "error-task"
        app.download_tasks[task_id] = {
            'progress': 0,
            'cancel_event': Event(),
            'thread': None,
            'status': "running",
            'url': "https://example.com",
            'directory': self.temp_dir
        }
        
        # Run the task (should catch the exception)
        app.download_task(
            url="https://example.com",
            directory=self.temp_dir,
            password=None,
            task_id=task_id
        )
        
        # Check that error was recorded
        self.assertEqual(app.download_tasks[task_id]['status'], "error")
        self.assertIn("Test error", app.download_tasks[task_id]['error_message'])
