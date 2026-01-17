#!/usr/bin/env python3
"""
GoFile API Test Script

This script tests the GoFile API connectivity and verifies that authentication,
token extraction, and content access are working correctly.

Usage:
    # Using environment variables (recommended for CI/CD)
    export GOFILE_TEST_URL="https://gofile.io/d/YOUR_CONTENT_ID"
    export GOFILE_TEST_PASSWORD="your_password"  # Optional
    python test_gofile_api.py

    # Using command-line arguments
    python test_gofile_api.py --url "https://gofile.io/d/YOUR_CONTENT_ID"
    python test_gofile_api.py --url "https://gofile.io/d/YOUR_CONTENT_ID" --password "your_password"

    # Skip password prompt
    python test_gofile_api.py --url "https://gofile.io/d/YOUR_CONTENT_ID" --no-password

Note: Do not commit URLs or passwords to version control. Use environment variables.
"""

import argparse
import hashlib
import os
import sys
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required.")
    print("Install it with: pip install requests")
    sys.exit(1)


class GoFileAPITester:
    """Test GoFile API connectivity and authentication."""

    def __init__(self):
        self.token: Optional[str] = None
        self.wt: Optional[str] = None

    def test_token_acquisition(self) -> bool:
        """Test if we can acquire a guest token from GoFile API."""
        print("=" * 60)
        print("TEST 1: Token Acquisition")
        print("=" * 60)
        
        try:
            response = requests.post('https://api.gofile.io/accounts', timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'ok':
                self.token = data['data']['token']
                print(f"✓ Successfully acquired token: {self.token[:20]}...")
                print(f"  Account ID: {data['data'].get('id', 'N/A')}")
                print(f"  Tier: {data['data'].get('tier', 'N/A')}")
                return True
            else:
                print(f"✗ Failed to acquire token: {data}")
                return False
                
        except Exception as e:
            print(f"✗ Exception during token acquisition: {e}")
            return False

    def test_wt_extraction(self) -> bool:
        """Test if we can extract websiteToken (wt) from config.js."""
        print("\n" + "=" * 60)
        print("TEST 2: WebsiteToken (wt) Extraction")
        print("=" * 60)
        
        try:
            response = requests.get('https://gofile.io/dist/js/config.js', timeout=10)
            response.raise_for_status()
            config_js = response.text
            
            print(f"  config.js size: {len(config_js)} characters")
            
            if 'appdata.wt = "' in config_js:
                self.wt = config_js.split('appdata.wt = "')[1].split('"')[0]
                print(f"✓ Successfully extracted wt: {self.wt[:20]}...")
                return True
            else:
                print("✗ Could not find 'appdata.wt' in config.js")
                print(f"  First 200 chars: {config_js[:200]}")
                return False
                
        except Exception as e:
            print(f"✗ Exception during wt extraction: {e}")
            return False

    def test_content_access(self, url: str, password: Optional[str] = None) -> bool:
        """Test if we can access content with proper authentication."""
        print("\n" + "=" * 60)
        print("TEST 3: Content Access")
        print("=" * 60)
        
        # Extract content ID from URL
        if url.startswith("https://gofile.io/d/"):
            content_id = url.split("/")[-1]
        else:
            print(f"✗ Invalid URL format: {url}")
            print("  Expected format: https://gofile.io/d/CONTENT_ID")
            return False
        
        print(f"  Content ID: {content_id}")
        print(f"  Password protected: {'Yes' if password else 'No'}")
        
        # Prepare request parameters
        params = {}
        if password:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            params['password'] = password_hash
            print(f"  Password hash: {password_hash[:20]}...")
        
        try:
            response = requests.get(
                f'https://api.gofile.io/contents/{content_id}',
                headers={
                    'Authorization': f'Bearer {self.token}',
                    'X-Website-Token': self.wt
                },
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            print(f"  API Status: {data.get('status')}")
            
            if data.get('status') == 'ok':
                content_data = data['data']
                
                # Check password status
                password_status = content_data.get('passwordStatus', 'passwordOk')
                if password_status != 'passwordOk':
                    print(f"✗ Password issue: {password_status}")
                    return False
                
                print("✓ Successfully accessed content!")
                print(f"  Type: {content_data.get('type')}")
                print(f"  Name: {content_data.get('name')}")
                
                # Show children info
                children = content_data.get('children', {})
                print(f"  Children count: {len(children)}")
                
                if children:
                    print(f"  First few items:")
                    for i, (child_id, child) in enumerate(list(children.items())[:5]):
                        item_type = child.get('type', 'unknown')
                        item_name = child.get('name', 'unnamed')
                        # Truncate long names
                        if len(item_name) > 50:
                            item_name = item_name[:47] + "..."
                        print(f"    {i+1}. [{item_type}] {item_name}")
                    
                    if len(children) > 5:
                        print(f"    ... and {len(children) - 5} more items")
                
                return True
            else:
                print(f"✗ Failed to access content: {data}")
                if data.get('status') == 'error-notPremium':
                    print("  Note: This error may indicate the API structure has changed.")
                    print("  Ensure you're using the latest version of gofile-dl.")
                return False
                
        except Exception as e:
            print(f"✗ Exception during content access: {e}")
            return False

    def run_all_tests(self, url: str, password: Optional[str] = None) -> bool:
        """Run all tests in sequence."""
        print("\n" + "=" * 60)
        print("GOFILE API TEST SUITE")
        print("=" * 60)
        print(f"Target URL: {url}")
        print(f"Password: {'***' if password else 'None'}")
        print()
        
        results = []
        
        # Test 1: Token acquisition
        results.append(("Token Acquisition", self.test_token_acquisition()))
        
        if not results[-1][1]:
            print("\n✗ Cannot proceed without token. Aborting remaining tests.")
            return False
        
        # Test 2: WT extraction
        results.append(("WT Extraction", self.test_wt_extraction()))
        
        if not results[-1][1]:
            print("\n✗ Cannot proceed without wt. Aborting remaining tests.")
            return False
        
        # Test 3: Content access
        results.append(("Content Access", self.test_content_access(url, password)))
        
        # Print summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        for test_name, passed in results:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"{status}: {test_name}")
        
        all_passed = all(result[1] for result in results)
        
        print("=" * 60)
        if all_passed:
            print("✓ ALL TESTS PASSED")
            print("=" * 60)
            return True
        else:
            print("✗ SOME TESTS FAILED")
            print("=" * 60)
            return False


def main():
    """Main entry point for the test script."""
    parser = argparse.ArgumentParser(
        description="Test GoFile API connectivity and authentication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with environment variables
  export GOFILE_TEST_URL="https://gofile.io/d/abc123"
  python test_gofile_api.py

  # Test with command-line arguments
  python test_gofile_api.py --url "https://gofile.io/d/abc123"
  python test_gofile_api.py --url "https://gofile.io/d/abc123" --password "mypass"

Note: Never commit real URLs or passwords to version control!
        """
    )
    
    parser.add_argument(
        '--url',
        type=str,
        help='GoFile URL to test (format: https://gofile.io/d/CONTENT_ID)'
    )
    parser.add_argument(
        '--password',
        type=str,
        help='Password for protected content (optional)'
    )
    parser.add_argument(
        '--no-password',
        action='store_true',
        help='Skip password prompt for non-protected content'
    )
    
    args = parser.parse_args()
    
    # Get URL from args or environment
    url = args.url or os.environ.get('GOFILE_TEST_URL')
    
    if not url:
        print("Error: No URL provided.")
        print()
        print("Provide a URL using one of these methods:")
        print("  1. Command-line argument: --url \"https://gofile.io/d/CONTENT_ID\"")
        print("  2. Environment variable: export GOFILE_TEST_URL=\"https://gofile.io/d/CONTENT_ID\"")
        print()
        parser.print_help()
        sys.exit(1)
    
    # Get password from args, environment, or prompt
    password = args.password or os.environ.get('GOFILE_TEST_PASSWORD')
    
    if not password and not args.no_password:
        try:
            password_input = input("Enter password (press Enter if content is not password-protected): ").strip()
            password = password_input if password_input else None
        except (KeyboardInterrupt, EOFError):
            print("\nTest cancelled.")
            sys.exit(1)
    
    # Run tests
    tester = GoFileAPITester()
    success = tester.run_all_tests(url, password)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
