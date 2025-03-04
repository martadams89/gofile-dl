from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
import threading, uuid
from threading import Event
from run import GoFile
import time
import shutil
import yaml
from typing import Dict, Any, Optional, List, Union
from flask_wtf import CSRFProtect
from functools import wraps
import secrets
from dotenv import load_dotenv
import platform
import psutil

# Load environment variables from .env file if it exists
load_dotenv()

# Environment variable validation
def get_env_var(var_name: str, default: Any = None, required: bool = False, 
                type_func: Optional[callable] = None) -> Any:
    """
    Get and validate environment variables with type conversion and validation
    
    Args:
        var_name: Name of environment variable
        default: Default value if not present
        required: Whether the variable is required
        type_func: Function to convert value to desired type
        
    Returns:
        The environment variable value with proper type
        
    Raises:
        ValueError: If required variable is missing or conversion fails
    """
    value = os.environ.get(var_name)
    
    if value is None:
        if required:
            raise ValueError(f"Required environment variable {var_name} is missing")
        return default
        
    if type_func is not None:
        try:
            return type_func(value)
        except Exception as e:
            raise ValueError(f"Failed to convert {var_name}={value} using {type_func.__name__}: {str(e)}")
    
    return value

# Load configuration
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.yml")
DEFAULT_CONFIG = {
    "port": 2355,
    "host": "0.0.0.0",
    "base_dir": "/app",
    "secret_key": secrets.token_hex(16),
    "default_retries": 3,
    "retry_delay": 5,
    "log_level": "INFO",
    "auth": {
        "enabled": False,
        "username": "admin",
        "password": "change-me-in-production"
    },
    "csrf": {
        "enabled": True,
        "time_limit": 3600  # 1 hour
    }
}

try:
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f)
    if not config:
        config = DEFAULT_CONFIG
except (FileNotFoundError, yaml.YAMLError):
    config = DEFAULT_CONFIG
    # Write default config if none exists
    try:
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
    except:
        pass  # Fail silently if can't write default config

# Override with environment variables if present
config["port"] = get_env_var("PORT", config["port"], False, int)
config["host"] = get_env_var("HOST", config["host"])
config["base_dir"] = get_env_var("BASE_DIR", config["base_dir"])
config["secret_key"] = get_env_var("SECRET_KEY", config["secret_key"])
config["auth"]["enabled"] = get_env_var("AUTH_ENABLED", config["auth"]["enabled"], False, lambda x: x.lower() == "true")
config["auth"]["username"] = get_env_var("AUTH_USERNAME", config["auth"]["username"])
config["auth"]["password"] = get_env_var("AUTH_PASSWORD", config["auth"]["password"])

app = Flask(__name__)
app.secret_key = config["secret_key"]

# Enable CSRF protection
csrf = CSRFProtect(app)
csrf.init_app(app)

# Global dict to track download tasks
download_tasks: Dict[str, Dict[str, Any]] = {}

# Basic authentication
def check_auth(username, password):
    """Check if username and password are valid"""
    if not config["auth"]["enabled"]:
        return True
    return username == config["auth"]["username"] and password == config["auth"]["password"]

def authenticate():
    """Send a 401 response requesting basic auth"""
    return Response(
        'Authentication required\n',
        401,
        {'WWW-Authenticate': 'Basic realm="gofile-dl"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config["auth"]["enabled"]:
            return f(*args, **kwargs)
            
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    # Collect basic system information
    system_info = {
        'system': platform.system(),
        'python_version': platform.python_version(),
        'cpu_usage': psutil.cpu_percent(interval=0.1),
        'memory': {
            'total': psutil.virtual_memory().total,
            'available': psutil.virtual_memory().available,
            'percent': psutil.virtual_memory().percent,
        },
        'disk': {
            'total': psutil.disk_usage('/').total,
            'free': psutil.disk_usage('/').free,
            'percent': psutil.disk_usage('/').percent,
        }
    }
    
    # Application status
    app_info = {
        'status': 'healthy',
        'active_tasks': sum(1 for task in download_tasks.values() 
                           if task.get('status') == 'running' or task.get('status') == 'paused'),
        'version': '1.0.0',  # Should be dynamically determined in production
    }
    
    # Return combined status
    return jsonify({
        'status': 'ok',
        'timestamp': time.time(),
        'system': system_info,
        'application': app_info
    })

def download_task(url: str, directory: Optional[str], password: Optional[str], task_id: str) -> None:
    """
    Background task for downloading GoFile content.
    
    Args:
        url: GoFile URL to download
        directory: Destination directory (or None for default)
        password: Password for protected content (or None)
        task_id: Unique ID for tracking this download task
    """
    def progress_callback(percentage):
        download_tasks[task_id]['progress'] = percentage
    
    def name_cb(new_name):
        out_dir = directory if directory else "./output"
        full_path = os.path.join(out_dir, new_name)
        download_tasks[task_id].update({'name': new_name, 'out_path': full_path})
    
    download_tasks[task_id]['files'] = []  # each element: {'file': filename, 'progress': 0}
    
    def file_progress_callback(filename, percentage, size=None):
        file_list = download_tasks[task_id]['files']
        for record in file_list:
            if record['file'] == filename:
                record['progress'] = percentage
                if size is not None:  # Update size if provided
                    record['size'] = size
                break
        else:
            new_record = {'file': filename, 'progress': percentage}
            if size is not None:
                new_record['size'] = size
            file_list.append(new_record)
    
    cancel_event = download_tasks[task_id]['cancel_event']
    
    # Define pause callback that checks the task's paused flag
    def pause_callback():
        return download_tasks[task_id].get('paused', False)
    
    output_dir = directory if directory else "./output"
    start_time = time.time()
    
    def overall_progress_callback(percent, eta):
        download_tasks[task_id]['overall_progress'] = percent
        download_tasks[task_id]['eta'] = eta
    
    # Get throttle and retries from the task config
    throttle_speed = download_tasks[task_id].get('throttle')
    retry_attempts = download_tasks[task_id].get('retries', 3)
    
    try:
        GoFile().execute(
            dir=output_dir, url=url, password=password,
            progress_callback=progress_callback, cancel_event=cancel_event,
            name_callback=name_cb, overall_progress_callback=overall_progress_callback,
            start_time=start_time, file_progress_callback=file_progress_callback,
            pause_callback=pause_callback, throttle_speed=throttle_speed,
            retry_attempts=retry_attempts
        )
        download_tasks[task_id]['status'] = "completed"
    except Exception as e:
        print(f"Task {task_id} error: {e}")
        download_tasks[task_id]['error_message'] = str(e)
        if cancel_event.is_set():
            download_tasks[task_id]['status'] = "cancelled"
        else:
            download_tasks[task_id]['status'] = "error"
    download_tasks[task_id]['progress'] = 100

@app.route('/tasks', methods=['GET'])
@requires_auth
def tasks():
    return jsonify({
        task_id: {
            'progress': task.get('progress', 0),
            'overall_progress': task.get('overall_progress', 0),
            'eta': task.get('eta', "N/A"),
            'status': task.get('status', 'running'),
            'error_message': task.get('error_message', ""),
            'url': task.get('url', ""),
            'name': task.get('name', ""),
            'timestamp': task.get('timestamp', 0),
            'files': task.get('files', []),
            'paused': task.get('paused', False)
        } for task_id, task in download_tasks.items()
    })

@app.route('/pause/<task_id>', methods=['POST'])
@requires_auth
def pause(task_id):
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Invalid task id"}), 404
    
    # Toggle the paused flag and update the status
    task['paused'] = not task.get('paused', False)
    status = "paused" if task['paused'] else "running"
    task['status'] = status
    
    return jsonify({
        "task_id": task_id, 
        "paused": task['paused'],
        "status": status
    })

def secure_path(base, target):
    # Ensure target is within base
    base = os.path.abspath(base)
    target = os.path.abspath(target)
    if os.path.commonpath([base, target]) != base:
        return base
    return target

@app.route('/browse', methods=['GET'])
@requires_auth
def browse():
    # Instead of restricting to a base directory, default BASE_DIR to "/" for full filesystem browsing
    base_dir = os.environ.get("BASE_DIR", "/")
    rel_path = request.args.get("path", "")
    if rel_path.strip() == "/":
        rel_path = ""
    # Remove secure_path restriction – allow navigating anywhere
    target_dir = os.path.join(base_dir, rel_path)
    if not os.path.isdir(target_dir):
        return jsonify({"error": "Invalid path"}), 400
    dirs = []
    for item in os.listdir(target_dir):
        fullpath = os.path.join(target_dir, item)
        if os.path.isdir(fullpath):
            dirs.append(item)
    return jsonify({"directories": dirs, "current": os.path.abspath(target_dir)})

@app.route('/start', methods=['POST'])
@requires_auth
def start_download():
    url = request.form.get('url')
    directory = request.form.get('directory')
    password = request.form.get('password')
    
    # Get new throttle and retry parameters
    try:
        throttle = int(request.form.get('throttle')) if request.form.get('throttle') else None
    except ValueError:
        throttle = None
        
    try:
        retries = min(max(0, int(request.form.get('retries', 3))), 10)  # Limit to 0-10
    except ValueError:
        retries = 3  # Default to 3 retries
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    task_id = str(uuid.uuid4())
    # Compute a friendly task name from directory or URL
    if directory:
        name = os.path.basename(directory.rstrip("/\\"))
        if not name:
            name = "download"
    else:
        name = url.split("/")[-1] if "/" in url else url
    
    download_tasks[task_id] = {
        'progress': 0,
        'cancel_event': Event(),
        'thread': None,
        'status': "running",
        'url': url,
        'directory': directory,
        'timestamp': time.time(),
        'name': name,
        'paused': False,
        'throttle': throttle,
        'retries': retries
    }
    
    thread = threading.Thread(target=download_task, args=(url, directory, password, task_id))
    download_tasks[task_id]['thread'] = thread
    thread.start()
    
    return jsonify({"task_id": task_id}), 202

@app.route('/progress/<task_id>', methods=['GET'])
@requires_auth
def progress(task_id):
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Invalid task id"}), 404
    return jsonify({"task_id": task_id, "progress": task['progress']})

@app.route('/cancel/<task_id>', methods=['POST'])
@requires_auth
def cancel(task_id):
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Invalid task id"}), 404
    task['cancel_event'].set()
    return jsonify({"task_id": task_id, "status": "cancelled"})

@app.route('/remove/<task_id>', methods=['POST'])
@requires_auth
def remove(task_id):
    if task_id in download_tasks:
        del download_tasks[task_id]
        return jsonify({"message": f"Task {task_id} removed."})
    else:
        return jsonify({"error": "Invalid task id"}), 404

@app.route('/delete/<task_id>', methods=['POST'])
@requires_auth
def delete(task_id):
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Invalid task id"}), 404
    out_path = task.get('out_path')
    if not out_path or not os.path.exists(out_path):
        # Remove task from global dict if files not exist.
        download_tasks.pop(task_id, None)
        return jsonify({"message": "Files already removed or not found; task removed."})
    try:
        if os.path.isdir(out_path):
            shutil.rmtree(out_path)
        else:
            os.remove(out_path)
        # Remove the task from tracking.
        download_tasks.pop(task_id, None)
        return jsonify({"message": f"Task {task_id} files deleted and task removed."})
    except FileNotFoundError:
        download_tasks.pop(task_id, None)
        return jsonify({"message": "Files already removed; task removed."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET', 'POST'])
@requires_auth
def index():
    if request.method == 'POST':
        url = request.form.get('url')
        directory = request.form.get('directory')
        password = request.form.get('password')
        if not url:
            flash("URL is required", "danger")
            return redirect(url_for('index'))
        # Instead of starting thread directly, call /start via redirect (or use AJAX)
        return redirect(url_for('index'))
    # Use BASE_DIR from env, default to container's /app
    base_dir = os.environ.get("BASE_DIR", "/app")
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    directories = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    return render_template('index.html', directories=directories)

if __name__ == '__main__':
    # Ensure proper environment variables are set
    port = get_env_var("PORT", config.get("port", 2355), False, int)
    host = get_env_var("HOST", config.get("host", "0.0.0.0"))
    debug = get_env_var("DEBUG", config.get("debug", False), False, lambda x: x.lower() == "true")
    
    app.run(host=host, port=port, debug=debug)
