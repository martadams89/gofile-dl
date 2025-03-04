import unittest
import json
import os
import time
from app import app, download_tasks

class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        # Clear tasks before each test
        download_tasks.clear()

    def test_index(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"GoFile Downloader", response.data)

    def test_browse(self):
        response = self.client.get("/browse?path=")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIsInstance(data, dict)
        self.assertIn("directories", data)

    def test_start_missing_url(self):
        response = self.client.post("/start", data={})
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("error", data)

    def test_tasks_endpoint_empty(self):
        response = self.client.get("/tasks")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        # Tasks dict may be empty initially.
        self.assertIsInstance(data, dict)

    def test_fake_delete_missing_file(self):
        # Create a fake task with an out_path that doesn't exist.
        task_id = "fake-task"
        download_tasks[task_id] = {
            'progress': 100,
            'overall_progress': 100,
            'eta': "N/A",
            'status': "completed",
            'url': "https://gofile.io/d/fake",
            'name': "Fake Task",
            'timestamp': time.time(),
            'out_path': "non_existing_path"
        }
        response = self.client.post(f"/delete/{task_id}")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("Files already removed", data.get("message"))

    def test_cancel_endpoint(self):
        # Create a fake task for cancellation.
        task_id = "cancel-task"
        download_tasks[task_id] = {
            'progress': 50,
            'overall_progress': 50,
            'eta': "N/A",
            'status': "running",
            'url': "https://gofile.io/d/fake",
            'name': "Cancel Task",
            'timestamp': time.time(),
            'cancel_event': type('FakeEvent', (), {"set": lambda self: None, "is_set": lambda self: True})()
        }
        response = self.client.post(f"/cancel/{task_id}")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data.get("status"), "cancelled")

if __name__ == '__main__':
    unittest.main()