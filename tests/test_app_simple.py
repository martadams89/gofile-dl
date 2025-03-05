import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys
import tempfile
import yaml
import threading
from threading import Event

# Add parent directory to path to import app module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

class AppSimpleTest(unittest.TestCase):
    """Simple tests to maximize app.py coverage"""
    
    def setUp(self):
        self.app = app.app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        app.config["auth"]["enabled"] = False
        self.client = self.app.test_client()
        self.original_config = app.config.copy()
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        app.config = self.original_config
        import shutil
        shutil.rmtree(self.temp_dir)
        app.download_tasks = {}
    
    def test_config_loading(self):
        """Test configuration loading"""
        test_config = {
            "port": 8080,
            "host": "127.0.0.1",
            "auth": {
                "enabled": True,
                "username": "testuser",
                "password": "testpass"
            }
        }
        
        # Mock yaml.safe_load and file opening for config loading
        with patch('yaml.safe_load', return_value=test_config):
            with patch('builtins.open'):
                app.config = app.DEFAULT_CONFIG.copy()
                app.load_config()  # Implement this function to extract config loading
                
                self.assertEqual(app.config["port"], 8080)
                self.assertEqual(app.config["host"], "127.0.0.1")
                self.assertTrue(app.config["auth"]["enabled"])
    
    @patch('app.GoFile')
    def test_error_handling_in_tasks(self, mock_gofile_class):
        """Test error handling in download tasks"""
        # Set up mock that will raise an exception
        mock_gofile = MagicMock()
        mock_gofile.execute.side_effect = Exception("Test error")
        mock_gofile_class.return_value = mock_gofile
        
        # Create test task
        task_id = "error-test"
        app.download_tasks[task_id] = {
            'progress': 0,
            'cancel_event': Event(),
            'thread': None,
            'status': "running",
            'url': "https://example.com",
            'directory': self.temp_dir
        }
        
        # Run task directly (should catch the exception)
        app.download_task(
            url="https://example.com",
            directory=self.temp_dir,
            password=None,
            task_id=task_id
        )
        
        # Check error was recorded correctly
        self.assertEqual(app.download_tasks[task_id]['status'], "error")
        self.assertEqual(app.download_tasks[task_id]['error_message'], "Test error")
    
    @patch('app.psutil.cpu_percent')
    @patch('app.psutil.virtual_memory')
    @patch('app.psutil.disk_usage')
    def test_health_check(self, mock_disk, mock_memory, mock_cpu):
        """Test health check endpoint with mocked system info"""
        # Mock system metrics
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
        
        # Test health endpoint
        response = self.client.get('/health')
        data = json.loads(response.data)
        
        # Basic checks
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'ok')
        
        # Check system metrics
        self.assertEqual(data['system']['cpu_usage'], 25.5)
        self.assertEqual(data['system']['memory']['percent'], 50.0)
