# Premium Account Token Support - Implementation Guide

## Overview
Added support for GoFile premium account tokens to bypass the `error-notPremium` API restrictions introduced in March 2026.

## Why This Feature?
- GoFile now restricts the `/contents/{id}` API endpoint to premium accounts
- Free accounts use a web scraping fallback which is slower
- Premium users can now use their account tokens for direct, faster API access
- Provides better reliability and performance for premium subscribers

## Changes Made

### 1. Core GoFile Class (`run.py`)

#### Modified `__init__` method:
```python
def __init__(self, premium_token: Optional[str] = None) -> None:
    self.token: str = ""
    self.wt: str = ""
    self.premium_token: Optional[str] = premium_token
    self.is_premium: bool = premium_token is not None
```

#### Updated `update_token()` method:
- Checks if premium token is provided
- Uses premium token instead of creating guest account
- Logs when using premium account

#### Enhanced error handling in `execute()`:
- Detects if premium token was provided but still got error-notPremium
- Provides specific error message for invalid premium tokens
- Falls back to web scraping only for free accounts

### 2. Configuration Support (`app.py`)

#### Added to default config:
```python
DEFAULT_CONFIG = {
    # ... other config ...
    "premium_token": None,  # Optional: Premium account token
}
```

#### Environment variable support:
```python
config["premium_token"] = get_env_var("GOFILE_PREMIUM_TOKEN", config.get("premium_token"))
```

### 3. Web Interface (`templates/index.html`)

Added premium token field in the Advanced Options section:
- Password input field for security
- Icon indicator (⭐) for premium feature
- Helper text with link to GoFile profile page
- Explains benefits of premium accounts

Location: Under "Advanced Options" collapsible section

### 4. Download Task Integration (`app.py`)

#### Modified `start_download()`:
- Accepts premium token from form
- Overrides config token if provided in form
- Passes token to download task

#### Modified `download_task()`:
- Retrieves premium token from task config or global config
- Passes token to GoFile instance

### 5. Documentation (`README.md`)

Added comprehensive section:
- "Premium Account Support" section with benefits
- Instructions for three configuration methods
- Environment variable in docker-compose example
- Added to environment variables table

## Usage Examples

### Method 1: Environment Variable (Docker)
```yaml
environment:
  - GOFILE_PREMIUM_TOKEN=your-premium-token-here
```

### Method 2: Config File
```yaml
# config.yml
premium_token: "your-premium-token-here"
```

### Method 3: Web Interface
1. Start a download
2. Click "Advanced Options"
3. Enter token in "GoFile Premium Account Token" field
4. Submit download

### Method 4: CLI (programmatic)
```python
from run import GoFile

gofile = GoFile(premium_token="your-premium-token-here")
gofile.execute(dir="./downloads", url="https://gofile.io/d/abc123")
```

## How to Get Your Premium Token

1. Log into your GoFile account
2. Go to [gofile.io/myProfile](https://gofile.io/myProfile)
3. Find your account token in the profile settings
4. Copy and use in any of the configuration methods above

## Benefits of Premium Tokens

1. **Performance**: Direct API access, no web scraping fallback needed
2. **Reliability**: No risk of web scraping being blocked
3. **Speed**: Faster content metadata retrieval
4. **Future-proof**: Less affected by GoFile UI changes

## Priority System

The token is selected in this priority order:
1. Token entered in web UI form (per-download)
2. Token from environment variable `GOFILE_PREMIUM_TOKEN`
3. Token from `config.yml`
4. If none provided, creates guest account (uses fallback)

## Error Handling

### Invalid Premium Token
If a premium token is provided but the API still returns `error-notPremium`:
```
[ERROR] Premium account returned error-notPremium. Check if token is valid.
[ERROR] API error: {'status': 'error-notPremium', 'data': {}}
```

### No Premium Token
If no premium token is provided:
- Creates guest account automatically
- Uses web scraping fallback if needed
- No change in behavior from previous version

## Testing

To test premium token support:

1. **With valid premium token**:
   ```bash
   GOFILE_PREMIUM_TOKEN=your-token python3 run.py https://gofile.io/d/abc123 -d ./downloads
   ```
   Expected: Direct API access, no fallback

2. **Without premium token**:
   ```bash
   python3 run.py https://gofile.io/d/abc123 -d ./downloads
   ```
   Expected: Guest account, web fallback if needed

3. **With invalid premium token**:
   ```bash
   GOFILE_PREMIUM_TOKEN=invalid python3 run.py https://gofile.io/d/abc123 -d ./downloads
   ```
   Expected: Error message about invalid token

## Security Considerations

1. **Token Storage**: Tokens are stored in config files and environment variables
   - Config file should have appropriate permissions (600)
   - Environment variables are secure in Docker

2. **Web Interface**: Token input is a password field
   - Not visible in browser
   - Stored only in task session, not persisted

3. **Logging**: Premium token is truncated in logs
   - Only first 20 characters shown
   - Example: `Using premium account token: AbCdEfGhIjKlMnOpQrSt...`

## Files Modified

1. **run.py**: 
   - Added `premium_token` parameter to `__init__`
   - Modified `update_token()` logic
   - Enhanced error handling in `execute()`

2. **app.py**:
   - Added premium_token to DEFAULT_CONFIG
   - Added GOFILE_PREMIUM_TOKEN env variable support
   - Modified `start_download()` to accept token
   - Modified `download_task()` to use token

3. **templates/index.html**:
   - Added premium token input field in Advanced Options
   - Added explanatory text and help

4. **README.md**:
   - Added Premium Account Support section
   - Updated environment variables table
   - Added token to docker-compose example

## Backwards Compatibility

✅ **Fully backwards compatible**
- Works without any premium token (uses guest account)
- No breaking changes to existing functionality
- All existing features continue to work
- Optional feature - doesn't affect non-premium users

## Future Enhancements

Potential improvements:
1. Token validation endpoint
2. Token refresh mechanism
3. Multiple token support (fallback tokens)
4. Token expiry detection and notification
5. Web UI token management (save/load)
