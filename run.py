import argparse
import logging
import os
from pathvalidate import sanitize_filename
import requests
import hashlib
import time
import math
from typing import Dict, List, Any, Optional, Callable, Union, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(funcName)20s()][%(levelname)-8s]: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("GoFile")

DEFAULT_TIMEOUT = 10  # 10 seconds

class GoFileMeta(type):
    """
    Metaclass for implementing the Singleton pattern.
    
    Ensures only one instance of GoFile is created.
    """
    _instances: Dict[type, Any] = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

class GoFile(metaclass=GoFileMeta):
    """
    GoFile API client for downloading files and folders.
    
    Provides methods to authenticate with the GoFile API and download content.
    Uses a Singleton pattern to ensure only one instance is created.
    """
    
    def __init__(self) -> None:
        """Initialize the GoFile client with empty token and wt."""
        self.token: str = ""
        self.wt: str = ""
    
    def count_files(self, children: Dict[str, Dict]) -> int:
        """
        Count the total number of files in a folder structure recursively.
        
        Args:
            children: Dictionary of child items from GoFile API response
            
        Returns:
            int: Total number of files found
        """
        count = 0
        for child in children.values():
            if child["type"] == "folder":
                count += self.count_files(child.get("children", {}))
            else:
                count += 1
        return count
    
    def update_token(self) -> None:
        """
        Update the access token used for API requests.
        
        Makes a request to GoFile's accounts API to get a fresh token.
        """
        if self.token == "":
            data = requests.post("https://api.gofile.io/accounts", timeout=DEFAULT_TIMEOUT).json()
            if data.get("status") == "ok":
                self.token = data["data"].get("token", "")
                logger.info(f"Updated token: {self.token}")
            else:
                logger.error("Cannot get token")
    
    def update_wt(self) -> None:
        """
        Update the 'wt' parameter needed for content requests.
        
        Extracts the wt parameter from GoFile's JavaScript code.
        """
        if self.wt == "":
            alljs = requests.get("https://gofile.io/dist/js/global.js", timeout=DEFAULT_TIMEOUT).text
            if 'appdata.wt = "' in alljs:
                self.wt = alljs.split('appdata.wt = "')[1].split('"')[0]
                logger.info(f"Updated wt: {self.wt}")
            else:
                logger.error("Cannot get wt")
    
    def execute(self, 
                dir: str, 
                content_id: Optional[str] = None, 
                url: Optional[str] = None, 
                password: Optional[str] = None,
                progress_callback: Optional[Callable[[int], None]] = None, 
                cancel_event: Optional[Any] = None, 
                name_callback: Optional[Callable[[str], None]] = None,
                overall_progress_callback: Optional[Callable[[int, str], None]] = None, 
                start_time: Optional[float] = None,
                file_progress_callback: Optional[Callable[[str, int, Optional[int]], None]] = None, 
                pause_callback: Optional[Callable[[], bool]] = None, 
                throttle_speed: Optional[int] = None,
                retry_attempts: int = 0) -> None:
        """
        Execute a download operation for a GoFile URL or content ID.
        
        This method handles both content IDs and URLs, authenticating as needed,
        and downloading either individual files or entire folder structures.
        
        Args:
            dir: Directory to save files to
            content_id: GoFile content ID
            url: GoFile URL (alternative to content_id)
            password: Optional password for protected content
            progress_callback: Callback for progress updates (0-100)
            cancel_event: Event to signal cancellation
            name_callback: Callback to update task name
            overall_progress_callback: Callback for overall progress updates (percent, ETA)
            start_time: Start time of the download
            file_progress_callback: Callback for file progress updates (filename, percent, size)
            pause_callback: Callback to check if download should pause
            throttle_speed: Download speed limit in KB/s
            retry_attempts: Number of retry attempts for failed downloads
        """
        if content_id is not None:
            self.update_token()
            self.update_wt()
            hash_password = hashlib.sha256(password.encode()).hexdigest() if password else ""
            response = requests.get(
                f"https://api.gofile.io/contents/{content_id}?wt={self.wt}&cache=true&password={hash_password}",
                headers={"Authorization": "Bearer " + self.token},
                timeout=DEFAULT_TIMEOUT
            )
            data = response.json()
            if data.get("status") != "ok":
                logger.error("API error: %s", data)
                return
            if data["data"].get("passwordStatus", "passwordOk") != "passwordOk":
                logger.error("Invalid password: %s", data["data"].get("passwordStatus"))
                return
            if data["data"]["type"] == "folder":
                dirname = data["data"]["name"]
                if name_callback:
                    name_callback(sanitize_filename(dirname))
                folder_path = os.path.join(dir, sanitize_filename(dirname))
                os.makedirs(folder_path, exist_ok=True)
                children = data["data"].get("children", {})
                if not children:
                    logger.error("No files/folders found in folder response: %s", data)
                    return
                overall_total = float(self.count_files(children))
                files_completed = 0.0
                for id, child in children.items():
                    if cancel_event and cancel_event.is_set():
                        break
                    try:
                        if child["type"] == "folder":
                            prev = float(self.count_files(child.get("children", {})))
                            self.execute(
                                dir=folder_path, content_id=id, password=password,
                                progress_callback=progress_callback, cancel_event=cancel_event,
                                name_callback=name_callback, overall_progress_callback=overall_progress_callback,
                                start_time=start_time, file_progress_callback=file_progress_callback,
                                pause_callback=pause_callback, throttle_speed=throttle_speed,
                                retry_attempts=retry_attempts
                            )
                            files_completed += prev
                        else:
                            filename = child["name"]
                            file_path = os.path.join(folder_path, sanitize_filename(filename))
                            link = child["link"]
                            if callable(file_progress_callback):
                                file_progress_callback(file_path, 0)  # register start (0%)
                            self.download(
                                link, file_path, progress_callback=progress_callback,
                                cancel_event=cancel_event, file_progress_callback=file_progress_callback,
                                pause_callback=pause_callback, throttle_speed=throttle_speed,
                                retry_attempts=retry_attempts
                            )
                            if callable(file_progress_callback):
                                file_progress_callback(file_path, 100)  # file complete
                            files_completed += 1.0
                    except Exception as e_inner:
                        logger.error(f"Error downloading child {id}: {e_inner}")
                        continue
                    if overall_progress_callback and overall_total > 0:
                        percent = int((files_completed / overall_total) * 100)
                        overall_progress_callback(percent, "N/A")
                if overall_progress_callback:
                    overall_progress_callback(100, "N/A")
            else:
                filename = data["data"]["name"]
                file_path = os.path.join(dir, sanitize_filename(filename))
                link = data["data"]["link"]
                if callable(name_callback):
                    name_callback(sanitize_filename(filename))
                if callable(file_progress_callback):
                    file_progress_callback(file_path, 0)
                self.download(link, file_path, progress_callback=progress_callback, cancel_event=cancel_event, file_progress_callback=file_progress_callback, pause_callback=pause_callback, throttle_speed=throttle_speed, retry_attempts=retry_attempts)
                if callable(file_progress_callback):
                    file_progress_callback(file_path, 100)
        elif url is not None:
            if url.startswith("https://gofile.io/d/"):
                cid = url.split("/")[-1]
                self.execute(dir=dir, content_id=cid, password=password,
                             progress_callback=progress_callback, cancel_event=cancel_event,
                             name_callback=name_callback, overall_progress_callback=overall_progress_callback,
                             start_time=start_time, file_progress_callback=file_progress_callback, pause_callback=pause_callback, throttle_speed=throttle_speed, retry_attempts=retry_attempts)
            else:
                logger.error(f"Invalid URL: {url}")
        else:
            logger.error("Invalid parameters")
    
    def download(self, 
                link: str, 
                file: str, 
                chunk_size: int = 8192, 
                progress_callback: Optional[Callable[[int], None]] = None,
                cancel_event: Optional[Any] = None, 
                file_progress_callback: Optional[Callable[[str, int, Optional[int]], None]] = None, 
                pause_callback: Optional[Callable[[], bool]] = None, 
                throttle_speed: Optional[int] = None,
                retry_attempts: int = 0, 
                retry_delay: int = 5) -> None:
        """
        Download a file from a GoFile link with various controls.
        
        Args:
            link: The file download link
            file: Path to save the file
            chunk_size: Size of download chunks in bytes
            progress_callback: Callback function to report download progress (0-100)
            cancel_event: Event to signal cancellation
            file_progress_callback: Callback to report file progress with size
            pause_callback: Callback to check if download should pause
            throttle_speed: Speed limit in KB/s (None for unlimited)
            retry_attempts: Number of retry attempts for failed downloads
            retry_delay: Seconds to wait between retry attempts
            
        Returns:
            None
            
        Raises:
            Exception: If the download fails after all retry attempts
        """
        temp = file + ".part"
        attempts = 0
        bytes_since_last_check = 0
        last_check_time = time.time()
        
        while attempts <= retry_attempts:
            try:
                file_dir = os.path.dirname(file)
                os.makedirs(file_dir, exist_ok=True)
                size = os.path.getsize(temp) if os.path.exists(temp) else 0
                with requests.get(
                    link, headers={
                        "Cookie": f"accountToken={self.token}",
                        "Range": f"bytes={size}-"
                    }, stream=True, timeout=DEFAULT_TIMEOUT
                ) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("Content-Length", 0)) + size
                    downloaded = size
                    
                    # Register file with its size information
                    if file_progress_callback:
                        file_progress_callback(file, 0, size=total_size)  # Pass size here
                    
                    with open(temp, "ab") as f:
                        for chunk in r.iter_content(chunk_size=chunk_size):
                            # Check for pause - if paused, wait until unpaused
                            if pause_callback and pause_callback():
                                while pause_callback():
                                    time.sleep(0.5)  # Sleep for half a second before checking again
                        
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                percentage = int(downloaded * 100 / total_size)
                                progress_callback(percentage)
                            if file_progress_callback:
                                file_progress_callback(file, int(downloaded * 100 / total_size), size=total_size)
                            if cancel_event and cancel_event.is_set():
                                logger.info("Download cancelled")
                                raise Exception("Cancelled")
                            
                            # Apply throttling if needed
                            if throttle_speed:
                                bytes_since_last_check += len(chunk)
                                current_time = time.time()
                                elapsed = current_time - last_check_time
                                
                                if elapsed > 0:  # Avoid division by zero
                                    current_rate = bytes_since_last_check / elapsed
                                    
                                    if current_rate > throttle_speed * 1024:
                                        # Need to sleep to maintain the desired rate
                                        sleep_time = (bytes_since_last_check / (throttle_speed * 1024)) - elapsed
                                        if sleep_time > 0:
                                            time.sleep(sleep_time)
                                        
                                        # Reset tracking after rate limiting
                                        bytes_since_last_check = 0
                                        last_check_time = time.time()
                    
                    # Rename temp file to final file when download is complete
                    os.rename(temp, file)
                    if file_progress_callback:
                        file_progress_callback(file, 100, size=total_size)
                    logger.info(f"Downloaded: {file} ({link})")
                    
                    # Download was successful, exit the retry loop
                    return
                    
            except Exception as e:
                attempts += 1
                logger.warning(f"Download attempt {attempts} failed for {file}: {e}")
                
                if attempts <= retry_attempts:
                    logger.info(f"Retrying in {retry_delay} seconds... ({attempts}/{retry_attempts})")
                    if file_progress_callback:
                        file_progress_callback(file, -1, retry_info=f"Retry {attempts}/{retry_attempts}")  # -1 indicates retry state
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to download after {attempts} attempts: {file} ({link})")
                    if os.path.exists(temp):
                        os.remove(temp)
                    if file_progress_callback:
                        file_progress_callback(file, -2)  # -2 indicates permanent failure
                    break

def main() -> None:
    """
    Main function for CLI usage.
    
    Parses command line arguments and initiates download.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("-d", type=str, dest="dir", help="output directory")
    parser.add_argument("-p", type=str, dest="password", help="password")
    args = parser.parse_args()
    out_dir = args.dir if args.dir is not None else "./output"
    GoFile().execute(dir=out_dir, url=args.url, password=args.password,
                      progress_callback=lambda p: logger.info(f"Overall progress: {p}%"),
                      overall_progress_callback=lambda p, eta: logger.info(f"Overall progress: {p}% | ETA: {eta}"),
                      name_callback=lambda name: logger.info(f"Task name set to: {name}"),
                      file_progress_callback=lambda f, p: logger.info(f"File {f} progress: {p}%"))
if __name__ == "__main__":
    main()