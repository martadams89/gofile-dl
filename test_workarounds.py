#!/usr/bin/env python3
"""
Script to test if GoFile content can be accessed through the web interface
instead of the API. This might be a workaround for the error-notPremium issue.
"""
import requests
from bs4 import BeautifulSoup
import json
import re

def test_web_scraping_approach():
    """
    Test if we can get content information through web scraping
    instead of API calls.
    """
    print("=" * 60)
    print("Testing Web Interface Approach")
    print("=" * 60)
    
    # Use a public test link (if you have one, replace 'test123')
    # For now, just testing the structure
    test_content_id = "test123"
    url = f"https://gofile.io/d/{test_content_id}"
    
    print(f"\nAttempting to access: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://gofile.io/'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response length: {len(response.text)} chars")
        
        # Look for JSON data in the page
        if 'contentId' in response.text:
            print("\n✓ Found contentId in page source")
        
        if 'wt' in response.text:
            print("✓ Found wt reference in page source")
        
        # Check if there's embedded JSON data
        json_pattern = re.findall(r'contentData\s*=\s*({.*?});', response.text, re.DOTALL)
        if json_pattern:
            print(f"\n✓ Found embedded content data")
            try:
                data = json.loads(json_pattern[0])
                print(f"   Keys: {list(data.keys())}")
            except:
                print("   (Could not parse JSON)")
        
        # Look for alternative data patterns
        if 'api.gofile.io' in response.text:
            print("\n✓ Page references API endpoints")
            
    except Exception as e:
        print(f"Error: {e}")

def check_api_alternatives():
    """Check if there are alternative API endpoints."""
    print("\n" + "=" * 60)
    print("Checking Alternative API Patterns")
    print("=" * 60)
    
    print("\nKnown GoFile API endpoints:")
    print("  - POST https://api.gofile.io/accounts (create account)")
    print("  - GET  https://api.gofile.io/contents/{id} (get content) [NOW RESTRICTED]")
    print("  - GET  https://api.gofile.io/servers (get upload servers)")
    
    print("\nPossible workarounds:")
    print("  1. Web scraping the gofile.io/d/{id} page")
    print("  2. Using a premium account token")
    print("  3. Looking for undocumented public endpoints")
    print("  4. Checking if download links work without content API")

if __name__ == '__main__':
    test_web_scraping_approach()
    check_api_alternatives()
    
    print("\n" + "=" * 60)
    print("CONCLUSION")
    print("=" * 60)
    print("\nGoFile has restricted the /contents/{id} API endpoint")
    print("to premium accounts only. Possible solutions:")
    print("\n  A) Implement web scraping to extract content info")
    print("  B) Support premium account tokens")
    print("  C) Find alternative public API endpoints")
    print("  D) Check if direct download links still work")
