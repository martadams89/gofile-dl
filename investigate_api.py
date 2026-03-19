#!/usr/bin/env python3
"""
Test script to understand the new GoFile API error.
The error-notPremium suggests GoFile may have restricted API access.
"""
import requests
import json
import time

def test_gofile_api():
    print("=" * 60)
    print("GoFile API Investigation - error-notPremium")
    print("=" * 60)
    
    # Step 1: Get account token
    print("\n1. Creating guest account...")
    time.sleep(2)  # Small delay
    try:
        response = requests.post('https://api.gofile.io/accounts', timeout=10)
        data = response.json()
        print(f"   Status: {data.get('status')}")
        
        if data.get('status') != 'ok':
            print(f"   Error creating account: {data}")
            return
        
        token = data['data']['token']
        tier = data['data'].get('tier', 'unknown')
        print(f"   Token: {token[:20]}...")
        print(f"   Account tier: {tier}")
        
    except Exception as e:
        print(f"   Failed: {e}")
        return
    
    # Step 2: Get website token
    print("\n2. Getting website token (wt)...")
    try:
        response = requests.get('https://gofile.io/dist/js/config.js', timeout=10)
        config_js = response.text
        
        if 'appdata.wt = "' in config_js:
            wt = config_js.split('appdata.wt = "')[1].split('"')[0]
            print(f"   WT: {wt}")
        else:
            print("   Warning: Could not find wt in config.js")
            wt = ""
    except Exception as e:
        print(f"   Failed: {e}")
        return
    
    # Step 3: Try accessing content with minimal headers
    print("\n3. Testing content access...")
    test_content_id = "abc123"  # Dummy ID to test API response
    
    headers = {
        'Authorization': f'Bearer {token}',
        'X-Website-Token': wt,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Origin': 'https://gofile.io',
        'Referer': 'https://gofile.io/'
    }
    
    time.sleep(2)  # Small delay
    try:
        response = requests.get(
            f'https://api.gofile.io/contents/{test_content_id}',
            headers=headers,
            timeout=10
        )
        result = response.json()
        print(f"   Status: {result.get('status')}")
        print(f"   Full response: {json.dumps(result, indent=4)}")
        
        if result.get('status') == 'error-notPremium':
            print("\n" + "!" * 60)
            print("FINDING: API returns 'error-notPremium'")
            print("!" * 60)
            print("\nThis indicates GoFile has restricted API access.")
            print("Possible causes:")
            print("  1. GoFile now requires premium accounts for API access")
            print("  2. Guest accounts can no longer use the contents endpoint")
            print("  3. Additional authentication is required")
            print("  4. API structure has fundamentally changed")
            
    except Exception as e:
        print(f"   Failed: {e}")
        return
    
    # Step 4: Check if there's an alternative endpoint
    print("\n4. Checking alternative endpoints...")
    time.sleep(2)
    
    # Try the old endpoint format (if it exists)
    try:
        response = requests.get(
            f'https://api.gofile.io/getContent?contentId={test_content_id}',
            headers=headers,
            timeout=10
        )
        result = response.json()
        print(f"   Old format response: {json.dumps(result, indent=4)}")
    except Exception as e:
        print(f"   Old format failed: {e}")

if __name__ == '__main__':
    test_gofile_api()
