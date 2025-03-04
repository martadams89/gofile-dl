from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import os
import threading, uuid
from threading import Event
from run import GoFile
import time
import shutil

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Change for production

# Global dict to track download tasks
download_tasks = {}  # task_id -> {'progress': 0, 'cancel_event': Event(), 'thread': Thread, 'status': str, ...}

def download_task(url, directory, password, task_id):
    def progress_callback(percentage):
        download_tasks[task_id]['progress'] = percentage
    
    def name_cb(new_name):
        out_dir = directory if directory else "./output"
        full_path = os.path.join(out_dir, new_name)
        download_tasks[task_id].update({'name': new_name, 'out_path': full_path})
    
    download_tasks[task_id]['files'] = []  # each element: {'file': filename, 'progress': 0}
    
    def file_progress_callback(filename, percentage):
        file_list = download_tasks[task_id]['files']
        for record in file_list:
            if record['file'] == filename:
                record['progress'] = percentage
                break
        else:
            file_list.append({'file': filename, 'progress': percentage})
    
    cancel_event = download_tasks[task_id]['cancel_event']
    
    # Define pause callback that checks the task's paused flag
    def pause_callback():
        return download_tasks[task_id].get('paused', False)
    
    output_dir = directory if directory else "./output"
    start_time = time.time()
    
    def overall_progress_callback(percent, eta):
        download_tasks[task_id]['overall_progress'] = percent
        download_tasks[task_id]['eta'] = eta
    
    try:
        GoFile().execute(
            dir=output_dir, url=url, password=password,
            progress_callback=progress_callback, cancel_event=cancel_event,
            name_callback=name_cb, overall_progress_callback=overall_progress_callback,
            start_time=start_time, file_progress_callback=file_progress_callback,
            pause_callback=pause_callback  # Pass the pause_callback to execute()
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
def start_download():
    url = request.form.get('url')
    directory = request.form.get('directory')
    password = request.form.get('password')
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
        'paused': False  # Initialize paused flag.
    }
    thread = threading.Thread(target=download_task, args=(url, directory, password, task_id))
    download_tasks[task_id]['thread'] = thread
    thread.start()
    return jsonify({"task_id": task_id}), 202

@app.route('/progress/<task_id>', methods=['GET'])
def progress(task_id):
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Invalid task id"}), 404
    return jsonify({"task_id": task_id, "progress": task['progress']})

@app.route('/cancel/<task_id>', methods=['POST'])
def cancel(task_id):
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Invalid task id"}), 404
    task['cancel_event'].set()
    return jsonify({"task_id": task_id, "status": "cancelled"})

@app.route('/remove/<task_id>', methods=['POST'])
def remove(task_id):
    if task_id in download_tasks:
        del download_tasks[task_id]
        return jsonify({"message": f"Task {task_id} removed."})
    else:
        return jsonify({"error": "Invalid task id"}), 404

@app.route('/delete/<task_id>', methods=['POST'])
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
    import os
    port = int(os.environ.get("PORT", 2355))
    app.run(host="0.0.0.0", port=port, debug=True)
