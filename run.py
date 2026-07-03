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

DEFAULT_TIMEOUT = 30  # 30 seconds - increased for slower connections
CONTENT_TIMEOUT = 45  # 45 seconds - for content API requests that may be slower

# --- Network access to GoFile ------------------------------------------------
# GoFile's API host (api.gofile.io) sits behind an edge that filters traffic by
# TLS fingerprint and IP reputation: it resets connections (curl error 35,
# "Connection reset by peer", right after the TLS Client Hello) from datacenter/
# VPN/flagged IPs and non-browser TLS stacks. When that happens, no token is
# even exchanged. Two mitigations are supported:
#
#   * GOFILE_PROXY   - route requests through an HTTP/SOCKS proxy on a clean
#                      (ideally residential) IP.
#   * curl_cffi      - if installed, impersonate a real Chrome TLS fingerprint,
#                      which gets past the fingerprint-based part of the filter.
#
# Both are optional; without them the tool uses plain `requests`, which is fine
# from a normal residential connection.
GOFILE_PROXY = os.environ.get("GOFILE_PROXY", "").strip() or None
GOFILE_IMPERSONATE = os.environ.get("GOFILE_IMPERSONATE", "chrome").strip()

try:
    from curl_cffi import requests as _cffi_requests  # type: ignore
    _HAS_CFFI = bool(GOFILE_IMPERSONATE) and GOFILE_IMPERSONATE.lower() != "off"
except ImportError:
    _cffi_requests = None
    _HAS_CFFI = False

# Exceptions that mean "GoFile's edge dropped us" (IP/TLS block), worth an
# explicit, actionable message rather than a generic stack trace.
_RESET_HINTS = ("reset by peer", "connection aborted", "err_empty_response",
                "recv failure", "curl: (35)", "curl: (56)")


def _is_connection_reset(exc: Exception) -> bool:
    """True if an exception looks like GoFile's edge resetting the connection."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(hint in text for hint in _RESET_HINTS)


def api_request(method: str, url: str, **kwargs: Any) -> Any:
    """
    Perform an HTTP request to a GoFile endpoint.

    Uses curl_cffi with browser TLS impersonation when available (to get past
    fingerprint-based filtering) and honors GOFILE_PROXY. Falls back to
    `requests`. The returned object exposes the requests-compatible attributes
    used here (`.status_code`, `.text`, `.headers`, `.json()`), and for
    streaming downloads `stream=True` plus `.iter_content()` / context-manager
    use.

    Args:
        method: HTTP method ("GET"/"POST").
        url: Target URL.
        **kwargs: Passed through (headers, params, timeout, stream, ...).

    Returns:
        The response object from curl_cffi or requests.
    """
    if GOFILE_PROXY:
        kwargs.setdefault("proxies", {"http": GOFILE_PROXY, "https": GOFILE_PROXY})
    if _HAS_CFFI and _cffi_requests is not None:
        return _cffi_requests.request(method, url, impersonate=GOFILE_IMPERSONATE, **kwargs)
    return requests.request(method, url, **kwargs)

# --- GoFile website-token (wt) generation -----------------------------------
# GoFile no longer accepts the static token published in config.js (that value
# is now a decoy). The real X-Website-Token is computed client-side in
# gofile.io/dist/js/wt.obf.js as:
#
#     sha256(f"{userAgent}::{language}::{accountToken}::{window}::{salt}")
#
# where `window = floor(unix_time / 14400)` is a rotating 4-hour bucket and
# `salt` is a secret embedded in wt.obf.js. The server recomputes and validates
# this token, so the User-Agent and language we hash MUST match the User-Agent
# and X-BL headers we actually send on the request.
#
# All three inputs can be overridden via environment variables so the tool can
# be kept working if GoFile rotates the salt or changes the UA expectations
# without needing a code change.
GOFILE_USER_AGENT = os.environ.get(
    "GOFILE_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)
GOFILE_LANGUAGE = os.environ.get("GOFILE_LANGUAGE", "en-US")
# Salt currently embedded in wt.obf.js. If GoFile rotates it and downloads start
# failing with "error-notPremium" again, update this value (or set the env var).
GOFILE_WT_SALT = os.environ.get("GOFILE_WT_SALT", "9844d94d963d30")
WT_WINDOW_SECONDS = 14400  # 4-hour rotating window used by GoFile

# Query parameters GoFile's web client now sends on every /contents request.
# pageSize is capped by GoFile; 1000 covers the vast majority of folders. Folders
# with more children would need pagination (see fetch_contents()).
CONTENTS_QUERY_PARAMS: Dict[str, Any] = {
    "contentFilter": "",
    "page": 1,
    "pageSize": 1000,
    "sortField": "createTime",
    "sortDirection": -1,
}


def generate_website_token(
    account_token: str,
    window_offset: int = 0,
    user_agent: str = GOFILE_USER_AGENT,
    language: str = GOFILE_LANGUAGE,
    salt: str = GOFILE_WT_SALT,
) -> str:
    """
    Reproduce GoFile's client-side X-Website-Token generation.

    Args:
        account_token: The account/guest token from POST /accounts.
        window_offset: Offset (in 4-hour windows) from the current time window.
            Used to retry with the previous window near a bucket boundary.
        user_agent: User-Agent string; must match the request's User-Agent.
        language: Language; must match the request's X-BL header.
        salt: Secret salt embedded in wt.obf.js.

    Returns:
        The 64-character hex website token.
    """
    window = int(time.time() // WT_WINDOW_SECONDS) + window_offset
    raw = f"{user_agent}::{language}::{account_token}::{window}::{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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

class GoFile:
    """
    GoFile API client for downloading files and folders.

    Provides methods to authenticate with the GoFile API and download content.

    A fresh instance should be created per download task: each holds its own
    account token, so this is safe to use from multiple threads concurrently.
    (Previously this class was a process-wide singleton, which leaked one task's
    premium token into other tasks and shared token state across threads.)
    """

    def __init__(self, premium_token: Optional[str] = None) -> None:
        """Initialize the GoFile client with empty token.

        Args:
            premium_token: Optional premium account token. If provided, uses premium
                         account instead of creating guest account.
        """
        self.token: str = ""
        self.premium_token: Optional[str] = premium_token
        self.is_premium: bool = premium_token is not None

    @staticmethod
    def parse_content_id(url: str) -> Optional[str]:
        """
        Extract a GoFile content ID from a URL or bare ID.

        Accepts full share URLs (http/https, with or without www, trailing
        slashes or query strings) as well as a bare content code.

        Args:
            url: A GoFile URL such as ``https://gofile.io/d/abc123`` or a bare id.

        Returns:
            The content ID, or None if it can't be determined.
        """
        if not url:
            return None
        candidate = url.strip()
        match = re.search(r"gofile\.io/d/([^/?#\s]+)", candidate, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        # Allow passing a bare content id (letters/digits, no scheme or path).
        if re.fullmatch(r"[A-Za-z0-9\-]+", candidate):
            return candidate
        return None
    
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
        
        If premium token is provided, uses that. Otherwise, creates a guest account.
        """
        if self.token == "":
            # Use premium token if provided
            if self.premium_token:
                self.token = self.premium_token
                logger.info(f"Using premium account token: {self.token[:20]}...")
            else:
                # Create guest account with retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        data = api_request(
                            "POST", "https://api.gofile.io/accounts",
                            headers={"User-Agent": GOFILE_USER_AGENT, "Origin": "https://gofile.io"},
                            timeout=DEFAULT_TIMEOUT,
                        ).json()
                        if data.get("status") == "ok":
                            self.token = data["data"].get("token", "")
                            logger.info(f"Updated token: {self.token}")
                            break
                        else:
                            logger.error("Cannot get token")
                    except requests.exceptions.Timeout:
                        if attempt < max_retries - 1:
                            logger.warning(f"Token request timed out, retrying ({attempt + 1}/{max_retries})...")
                            time.sleep(2)
                        else:
                            logger.error("Failed to get token after multiple attempts due to timeout")
                    except Exception as e:
                        if _is_connection_reset(e):
                            self._log_edge_block("account creation")
                            break
                        logger.error(f"Error getting token: {e}")
                        break
    
    def website_token(self, window_offset: int = 0) -> str:
        """
        Compute the X-Website-Token for the current account token.

        This replaces the old approach of scraping a static token from
        config.js, which GoFile turned into a decoy (it now returns
        "error-notPremium"). See generate_website_token() for the algorithm.

        Args:
            window_offset: 4-hour window offset, used to retry with the previous
                window near a time-bucket boundary.

        Returns:
            The 64-character hex website token, or "" if no token is set.
        """
        if not self.token:
            return ""
        return generate_website_token(self.token, window_offset=window_offset)

    def _content_headers(self, window_offset: int = 0) -> Dict[str, str]:
        """Build the headers GoFile expects for a /contents request."""
        return {
            "Authorization": "Bearer " + self.token,
            "X-Website-Token": self.website_token(window_offset),
            "X-BL": GOFILE_LANGUAGE,
            "User-Agent": GOFILE_USER_AGENT,
            "Accept": "*/*",
            "Origin": "https://gofile.io",
            "Referer": "https://gofile.io/",
        }

    @staticmethod
    def _log_edge_block(what: str) -> None:
        """Explain a connection reset from GoFile's API edge and how to fix it."""
        logger.error(f"GoFile reset the connection during {what} (api.gofile.io).")
        logger.error("This IP is blocked by GoFile's API edge - common on VPN,")
        logger.error("datacenter and cloud hosts. Remedies:")
        logger.error("  * run from a residential connection, or")
        logger.error("  * set GOFILE_PROXY to an HTTP/SOCKS proxy on a clean IP, or")
        logger.error("  * install curl_cffi (pip install curl_cffi) for browser TLS.")

    def get_content_from_web(self, content_id: str, password: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fallback method to extract content information from the GoFile web interface.
        
        This is used when the API returns error-notPremium, which indicates that
        the contents endpoint is restricted to premium accounts.
        
        The approach is to:
        1. Visit the gofile.io/d/{id} page to establish a session
        2. Extract any tokens/cookies from the page
        3. Make the API request as the browser would
        
        Args:
            content_id: GoFile content ID
            password: Optional password for protected content
            
        Returns:
            Content data dictionary similar to API response, or None if failed
        """
        try:
            url = f"https://gofile.io/d/{content_id}"
            logger.info(f"Attempting web fallback for content: {content_id}")
            
            # Create a session to maintain cookies
            session = requests.Session()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://gofile.io/',
            }
            
            # Step 1: Visit the page to get any session cookies
            response = session.get(url, headers=headers, timeout=CONTENT_TIMEOUT)
            response.raise_for_status()
            
            # Step 2: Try to make API request with the session cookies
            api_headers = dict(self._content_headers())
            api_headers['Referer'] = url

            # Build params
            params = dict(CONTENTS_QUERY_PARAMS)
            if password:
                hash_password = hashlib.sha256(password.encode()).hexdigest()
                params['password'] = hash_password

            # Try the API call again with browser-like impersonation/proxy
            api_response = api_request(
                "GET",
                f"https://api.gofile.io/contents/{content_id}",
                headers=api_headers,
                params=params,
                timeout=CONTENT_TIMEOUT,
                cookies=session.cookies.get_dict(),
            )

            data = api_response.json()
            
            if data.get("status") == "ok":
                logger.info("Web fallback successful with browser session")
                return data
            else:
                logger.warning(f"Web fallback API call returned: {data.get('status')}")
                
                # If still failing, try extracting from page source
                html_content = response.text
                import re
                
                # Look for embedded content data in various formats
                patterns = [
                    r'contentData\s*=\s*({.*?});',
                    r'var\s+content\s*=\s*({.*?});',
                    r'window\.contentData\s*=\s*({.*?});',
                    r'const\s+contentData\s*=\s*({.*?});',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, html_content, re.DOTALL)
                    if matches:
                        try:
                            content_json = json.loads(matches[0])
                            logger.info("Extracted content data from page source")
                            return {"status": "ok", "data": content_json}
                        except json.JSONDecodeError:
                            continue
                
                return None
            
        except Exception as e:
            logger.error(f"Web fallback failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

    def fetch_contents(self, content_id: str, password: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch a content listing from the GoFile API.

        Handles the current (2026) API requirements: a dynamically generated
        website token, the extra query parameters GoFile's web client sends, and
        the transient errors it can return (timeouts and rate limiting). Falls
        back to the previous 4-hour token window near a bucket boundary, and to
        web scraping as a last resort.

        Args:
            content_id: GoFile content ID.
            password: Optional password for protected content.

        Returns:
            Parsed API response dict with status == "ok", or None on failure.
        """
        params = dict(CONTENTS_QUERY_PARAMS)
        if password:
            params["password"] = hashlib.sha256(password.encode()).hexdigest()

        url = f"https://api.gofile.io/contents/{content_id}"
        max_attempts = 4
        # Try the current token window first, then the previous one (offset -1)
        # in case we're just past a 4-hour boundary but the server clock isn't.
        window_offsets = [0, -1]

        for attempt in range(max_attempts):
            window_offset = window_offsets[min(attempt, len(window_offsets) - 1)]
            try:
                response = api_request(
                    "GET",
                    url,
                    headers=self._content_headers(window_offset),
                    params=params,
                    timeout=CONTENT_TIMEOUT,
                )
                data = response.json()
            except requests.exceptions.Timeout:
                if attempt < max_attempts - 1:
                    logger.warning(f"Content request timed out, retrying ({attempt + 1}/{max_attempts})...")
                    time.sleep(3)
                    continue
                logger.error(f"Failed to fetch content {content_id} after {max_attempts} attempts due to timeout")
                logger.error("GoFile's API may be slow or overloaded. Try again later.")
                return None
            except Exception as e:
                if _is_connection_reset(e):
                    self._log_edge_block("content fetch")
                    # Web fallback also hits api.gofile.io, so it won't help here.
                    return None
                logger.error(f"Failed to fetch content {content_id}: {e}")
                return None

            status = data.get("status")
            if status == "ok":
                return data

            if status == "error-rateLimit":
                # GoFile rate-limits guest content requests; back off and retry.
                wait = 3 * (attempt + 1)
                if attempt < max_attempts - 1:
                    logger.warning(f"GoFile rate limit hit, waiting {wait}s before retry ({attempt + 1}/{max_attempts})...")
                    time.sleep(wait)
                    continue
                logger.error("GoFile rate limit persisted. Wait a few minutes and try again.")
                return None

            if status == "error-notPremium":
                # A correct website token is accepted by the server; getting this
                # means our token was rejected. Retry once with the previous
                # window, otherwise the embedded salt has likely rotated.
                if attempt == 0:
                    logger.warning("Got error-notPremium; retrying with previous token window...")
                    continue
                if self.is_premium:
                    logger.error("Premium account returned error-notPremium. Check that the token is valid.")
                    return None
                logger.warning("Website token rejected; attempting web fallback...")
                web_data = self.get_content_from_web(content_id, password)
                if web_data and web_data.get("status") == "ok":
                    logger.info("Successfully retrieved content via web fallback")
                    return web_data
                logger.error("Website token rejected (GoFile may have rotated its salt).")
                logger.error("Set GOFILE_WT_SALT to the current value, or update the tool.")
                logger.error("API error: %s", data)
                return None

            # Some transient errors are worth one more try.
            if status in ("error-notFound",):
                logger.error(f"Content {content_id} not found (it may have been deleted).")
                return None

            logger.error("API error: %s", data)
            return None

        return None

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

            # Initialize tracker for incremental mode
            if incremental and tracker is None:
                tracker = DownloadTracker(dir, content_id, folder_pattern)

            data = self.fetch_contents(content_id, password)
            if data is None:
                # fetch_contents already logged the specific reason.
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
            cid = self.parse_content_id(url)
            if cid:
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
                proxies = {"http": GOFILE_PROXY, "https": GOFILE_PROXY} if GOFILE_PROXY else None
                with requests.get(
                    link, headers={
                        "Cookie": f"accountToken={self.token}",
                        "User-Agent": GOFILE_USER_AGENT,
                        "Referer": "https://gofile.io/",
                        "Range": f"bytes={size}-"
                    }, stream=True, timeout=DEFAULT_TIMEOUT, proxies=proxies
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

    def cli_file_progress(f, p, size=None, retry_info=None):
        if retry_info:
            logger.info(f"File {f}: {retry_info}")
        elif p in (100, -2):
            logger.info(f"File {f} progress: {p}%")

    GoFile().execute(dir=out_dir, url=args.url, password=args.password,
                      overall_progress_callback=lambda p, folder: logger.info(f"Overall progress: {p}% | {folder}"),
                      name_callback=lambda name: logger.info(f"Task name set to: {name}"),
                      file_progress_callback=cli_file_progress)
if __name__ == "__main__":
    main()