import argparse
import logging
import os
from pathvalidate import sanitize_filename
import requests
import hashlib
import time
import re
import json
from typing import Dict, Any, Optional, Callable, Set

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(funcName)20s()][%(levelname)-8s]: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("GoFile")

DEFAULT_TIMEOUT = 10  # 10 seconds

def strip_emojis_func(text: str) -> str:
    """
    Remove emojis and other problematic Unicode characters from text.
    
    Args:
        text: Input string potentially containing emojis
        
    Returns:
        String with emojis removed
    """
    # Emoji pattern - covers most emoji ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002500-\U00002BEF"  # chinese char
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002600-\U000026FF"  # Miscellaneous Symbols
        "\U00002700-\U000027BF"  # Dingbats
        "]+",
        flags=re.UNICODE
    )
    result = emoji_pattern.sub('', text)
    # Clean up any double spaces or trailing/leading spaces
    result = ' '.join(result.split())
    return result.strip()

def normalize_folder_name(name: str, custom_patterns: Optional[str] = None) -> str:
    """
    Normalize folder name by removing common prefixes like 'NEW FILES in'.
    This helps match folders that get renamed after completion.
    
    Args:
        name: Original folder name
        custom_patterns: Optional pipe-separated list of patterns to strip (e.g., '⭐NEW FILES in |NEW FILES in |⭐')
        
    Returns:
        Normalized folder name
    """
    # Default patterns
    patterns = [
        r'^⭐\s*NEW FILES in\s+',
        r'^NEW FILES in\s+',
        r'^⭐\s*',
        r'^\*+\s*NEW FILES in\s+',
        r'^\*+\s*',
    ]
    
    # Add custom patterns if provided
    if custom_patterns:
        custom_list = [p.strip() for p in custom_patterns.split('|') if p.strip()]
        # Convert custom patterns to regex patterns (escape special chars except spaces)
        for pattern in custom_list:
            # Escape regex special characters but preserve the pattern intent
            escaped = re.escape(pattern)
            # Replace escaped spaces with flexible whitespace matcher
            escaped = escaped.replace('\\ ', '\\s*')
            # Add anchors and trailing whitespace matcher
            regex_pattern = f'^{escaped}\\s*'
            patterns.insert(0, regex_pattern)  # Insert at beginning for priority
    
    result = name
    for pattern in patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    return result.strip()

class DownloadTracker:
    """
    Tracks downloaded files to enable incremental/sync downloads.
    """
    
    def __init__(self, base_dir: str, content_id: str, folder_pattern: Optional[str] = None):
        """
        Initialize download tracker.
        
        Args:
            base_dir: Base directory for downloads
            content_id: GoFile content ID being tracked
            folder_pattern: Custom patterns to strip from folder names (pipe-separated)
        """
        self.base_dir = base_dir
        self.content_id = content_id
        self.folder_pattern = folder_pattern
        # Store tracking files in /config directory for persistence
        config_dir = os.environ.get('CONFIG_DIR', '/config')
        os.makedirs(config_dir, exist_ok=True)
        self.tracking_file = os.path.join(config_dir, f".gofile_tracker_{content_id}.json")
        self.downloaded_files: Set[str] = set()
        self.load_tracking_data()
    
    def load_tracking_data(self) -> None:
        """Load previously downloaded file list from tracking file."""
        if os.path.exists(self.tracking_file):
            try:
                with open(self.tracking_file, 'r') as f:
                    data = json.load(f)
                    self.downloaded_files = set(data.get('files', []))
                    logger.info(f"Loaded tracking data: {len(self.downloaded_files)} previously downloaded files")
            except Exception as e:
                logger.warning(f"Could not load tracking data: {e}")
                self.downloaded_files = set()
    
    def save_tracking_data(self) -> None:
        """Save downloaded file list to tracking file."""
        try:
            os.makedirs(os.path.dirname(self.tracking_file), exist_ok=True)
            with open(self.tracking_file, 'w') as f:
                json.dump({
                    'content_id': self.content_id,
                    'last_updated': time.time(),
                    'files': list(self.downloaded_files)
                }, f, indent=2)
            logger.debug(f"Saved tracking data: {len(self.downloaded_files)} files")
        except Exception as e:
            logger.warning(f"Could not save tracking data: {e}")
    
    def is_downloaded(self, file_id: str, file_name: str) -> bool:
        """
        Check if a file has already been downloaded.
        
        Args:
            file_id: GoFile file ID
            file_name: File name
            
        Returns:
            True if file was previously downloaded
        """
        key = f"{file_id}:{file_name}"
        return key in self.downloaded_files
    
    def mark_downloaded(self, file_id: str, file_name: str) -> None:
        """
        Mark a file as downloaded.
        
        Args:
            file_id: GoFile file ID
            file_name: File name
        """
        key = f"{file_id}:{file_name}"
        self.downloaded_files.add(key)
        self.save_tracking_data()
    
    def find_existing_folder(self, folder_name: str, parent_dir: str) -> Optional[str]:
        """
        Find an existing folder that matches the given name, handling renames.
        
        Args:
            folder_name: Current folder name
            parent_dir: Parent directory to search in
            
        Returns:
            Path to existing folder or None
        """
        if not os.path.exists(parent_dir):
            return None
        
        # Normalize the target folder name with custom pattern
        normalized_target = normalize_folder_name(folder_name, self.folder_pattern)
        
        # Check for exact match first
        exact_path = os.path.join(parent_dir, sanitize_filename(folder_name))
        if os.path.isdir(exact_path):
            return exact_path
        
        # Look for similar folders (normalized match)
        for item in os.listdir(parent_dir):
            item_path = os.path.join(parent_dir, item)
            if os.path.isdir(item_path):
                normalized_item = normalize_folder_name(item, self.folder_pattern)
                if normalized_item == normalized_target:
                    logger.info(f"Found renamed folder: '{item}' matches '{folder_name}'")
                    return item_path
        
        return None

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
        Count the total number of files in a folder structure.
        
        Note: This only counts files in the current level, not nested folders,
        since nested folder contents need separate API calls.
        
        Args:
            children: Dictionary of child items from GoFile API response
            
        Returns:
            int: Total number of files and folders found
        """
        count = 0
        for child in children.values():
            # Count each item (file or folder) as 1
            # We can't count nested folder contents without additional API calls
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
        Update the 'wt' (websiteToken) parameter needed for content requests.
        
        Extracts the wt parameter from GoFile's config.js JavaScript file.
        """
        if self.wt == "":
            try:
                alljs = requests.get("https://gofile.io/dist/js/config.js", timeout=DEFAULT_TIMEOUT).text
                if 'appdata.wt = "' in alljs:
                    self.wt = alljs.split('appdata.wt = "')[1].split('"')[0]
                    logger.info(f"Updated wt: {self.wt}")
                else:
                    logger.error("Cannot extract wt from config.js")
            except Exception as e:
                logger.error(f"Failed to get wt: {e}")
    
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
                retry_attempts: int = 0,
                strip_emojis: bool = False,
                incremental: bool = False,
                tracker: Optional[DownloadTracker] = None,
                folder_pattern: Optional[str] = None) -> None:
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
            strip_emojis: Whether to strip emojis from folder/file names
            incremental: Enable incremental mode (skip already downloaded files)
            tracker: Download tracker instance (created automatically if None)
            folder_pattern: Custom patterns to strip from folder names (pipe-separated)
        """
        if content_id is not None:
            self.update_token()
            self.update_wt()
            
            # Initialize tracker for incremental mode
            if incremental and tracker is None:
                tracker = DownloadTracker(dir, content_id, folder_pattern)
            
            # Build API request with proper parameters
            params = {}
            if password:
                hash_password = hashlib.sha256(password.encode()).hexdigest()
                params['password'] = hash_password
            
            try:
                response = requests.get(
                    f"https://api.gofile.io/contents/{content_id}",
                    headers={
                        "Authorization": "Bearer " + self.token,
                        "X-Website-Token": self.wt
                    },
                    params=params,
                    timeout=DEFAULT_TIMEOUT
                )
                data = response.json()
            except Exception as e:
                logger.error(f"Failed to fetch content {content_id}: {e}")
                return
            if data.get("status") != "ok":
                logger.error("API error: %s", data)
                return
            if data["data"].get("passwordStatus", "passwordOk") != "passwordOk":
                logger.error("Invalid password: %s", data["data"].get("passwordStatus"))
                return
            if data["data"]["type"] == "folder":
                dirname = data["data"]["name"]
                
                # Strip emojis if requested
                if strip_emojis:
                    dirname_clean = strip_emojis_func(dirname)
                    if not dirname_clean:  # If name becomes empty after stripping
                        dirname = f"folder_{content_id[:8]}"
                    else:
                        dirname = dirname_clean
                
                if name_callback:
                    name_callback(sanitize_filename(dirname))
                
                # Check for existing folder (handles renames in incremental mode)
                if incremental and tracker:
                    existing_folder = tracker.find_existing_folder(dirname, dir)
                    if existing_folder:
                        logger.info(f"Using existing folder: {existing_folder}")
                        folder_path = existing_folder
                    else:
                        folder_path = os.path.join(dir, sanitize_filename(dirname))
                else:
                    folder_path = os.path.join(dir, sanitize_filename(dirname))
                
                # Create folder with better error handling
                try:
                    os.makedirs(folder_path, exist_ok=True)
                except PermissionError as e:
                    logger.error(f"Permission denied creating folder '{folder_path}': {e}")
                    logger.error(f"Check that the parent directory is writable. Current user UID: {os.getuid()}")
                    raise PermissionError(f"Cannot create folder '{folder_path}': Permission denied. Check Docker volume permissions.")
                except OSError as e:
                    logger.error(f"OS error creating folder '{folder_path}': {e}")
                    raise OSError(f"Cannot create folder '{folder_path}': {e}")
                
                # Get children - they might be in 'children' or 'contents' depending on API version
                children = data["data"].get("children", {})
                if not children:
                    children = data["data"].get("contents", {})
                
                if not children:
                    logger.warning(f"No children found in folder {content_id} ({dirname})")
                    # Don't return - empty folders are valid
                    if overall_progress_callback:
                        folder_name = data["data"].get("name", "folder")
                        overall_progress_callback(100, folder_name)
                    return
                
                # Calculate progress for THIS folder only (not recursive)
                overall_total = float(len(children))
                files_completed = 0.0
                
                for child_id, child in children.items():
                    if cancel_event and cancel_event.is_set():
                        break
                    
                    try:
                        child_type = child.get("type", "file")
                        
                        if child_type == "folder":
                            # Recursively process subfolder
                            logger.info(f"Processing subfolder: {child.get('name', child_id)}")
                            
                            # Recursively download subfolder contents
                            # Note: Progress tracking for subfolders is approximate since we need
                            # to make API calls to get their contents
                            self.execute(
                                dir=folder_path, 
                                content_id=child_id, 
                                password=password,
                                progress_callback=progress_callback, 
                                cancel_event=cancel_event,
                                name_callback=None,  # Don't update main task name for subfolders
                                overall_progress_callback=overall_progress_callback,
                                start_time=start_time, 
                                file_progress_callback=file_progress_callback,
                                pause_callback=pause_callback, 
                                throttle_speed=throttle_speed,
                                retry_attempts=retry_attempts,
                                strip_emojis=strip_emojis,
                                incremental=incremental,
                                tracker=tracker,
                                folder_pattern=folder_pattern
                            )
                            files_completed += 1.0  # Count the folder as processed
                            
                        else:
                            # Download file
                            filename = child.get("name", "unknown")
                            
                            # Check if already downloaded in incremental mode
                            if incremental and tracker and tracker.is_downloaded(child_id, filename):
                                logger.info(f"Skipping already downloaded file: {filename}")
                                files_completed += 1.0
                                if callable(file_progress_callback):
                                    file_path = os.path.join(folder_path, sanitize_filename(filename))
                                    file_progress_callback(file_path, 100)
                                continue
                            
                            # Strip emojis if requested
                            if strip_emojis:
                                filename_clean = strip_emojis_func(filename)
                                if not filename_clean:  # If name becomes empty after stripping
                                    # Keep extension if present
                                    ext = os.path.splitext(filename)[1]
                                    filename = f"file_{child_id[:8]}{ext}"
                                else:
                                    filename = filename_clean
                            
                            file_path = os.path.join(folder_path, sanitize_filename(filename))
                            link = child.get("link", "")
                            
                            if not link:
                                logger.error(f"No download link for file: {filename}")
                                files_completed += 1.0
                                continue
                            
                            logger.info(f"Downloading file: {filename}")
                            
                            if callable(file_progress_callback):
                                file_progress_callback(file_path, 0)  # register start (0%)
                            
                            self.download(
                                link, file_path, 
                                progress_callback=progress_callback,
                                cancel_event=cancel_event, 
                                file_progress_callback=file_progress_callback,
                                pause_callback=pause_callback, 
                                throttle_speed=throttle_speed,
                                retry_attempts=retry_attempts
                            )
                            
                            # Mark as downloaded in incremental mode
                            if incremental and tracker:
                                tracker.mark_downloaded(child_id, filename)
                            
                            if callable(file_progress_callback):
                                file_progress_callback(file_path, 100)  # file complete
                            
                            files_completed += 1.0
                            
                    except Exception as e_inner:
                        logger.error(f"Error processing child {child_id}: {e_inner}")
                        files_completed += 1.0  # Count as processed even if failed
                        continue
                    
                    # Update progress after each child in this folder
                    if overall_progress_callback and overall_total > 0:
                        percent = int((files_completed / overall_total) * 100)
                        folder_name = data["data"].get("name", "folder")
                        overall_progress_callback(percent, folder_name)
                
                # Mark this folder as complete
                if overall_progress_callback:
                    folder_name = data["data"].get("name", "folder")
                    overall_progress_callback(100, folder_name)
            else:
                filename = data["data"]["name"]
                
                # Strip emojis if requested
                if strip_emojis:
                    filename_clean = strip_emojis_func(filename)
                    if not filename_clean:  # If name becomes empty after stripping
                        # Keep extension if present
                        ext = os.path.splitext(filename)[1]
                        filename = f"file_{content_id[:8]}{ext}"
                    else:
                        filename = filename_clean
                
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
                             start_time=start_time, file_progress_callback=file_progress_callback, pause_callback=pause_callback, throttle_speed=throttle_speed, retry_attempts=retry_attempts, strip_emojis=strip_emojis, incremental=incremental, tracker=tracker, folder_pattern=folder_pattern)
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