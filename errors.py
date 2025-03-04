"""Error handling classes for GoFile Downloader"""

class GoFileError(Exception):
    """Base exception class for GoFile operations"""
    pass

class AuthenticationError(GoFileError):
    """Failed to authenticate with GoFile API"""
    pass

class ContentNotFoundError(GoFileError):
    """Content ID or URL not found"""
    pass

class PasswordError(GoFileError):
    """Password is incorrect or required"""
    pass

class DownloadError(GoFileError):
    """Generic download error"""
    def __init__(self, message: str, filename: str, url: str):
        self.filename = filename
        self.url = url
        super().__init__(f"{message}: {filename} ({url})")

class ThrottleError(GoFileError):
    """Error in throttling configuration"""
    pass

class RetryExhaustedError(GoFileError):
    """All retry attempts have been exhausted"""
    pass
