#!/usr/bin/env python3
"""
Test script to verify the error-notPremium fix works.
This will test both the API call and the web fallback.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from run import GoFile
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s][%(funcName)20s()][%(levelname)-8s]: %(message)s",
)

def test_api_with_fallback():
    """Test that the web fallback works when API returns error-notPremium."""
    print("=" * 60)
    print("Testing API with Fallback for error-notPremium")
    print("=" * 60)
    
    gofile = GoFile()
    
    # Initialize tokens
    gofile.update_token()
    gofile.update_wt()
    
    print(f"\nToken: {gofile.token[:20]}...")
    print(f"WT: {gofile.wt}")
    
    # Test with a dummy content ID to trigger the fallback
    print("\n--- Testing with dummy content ID ---")
    content_id = "test123"
    
    # This should trigger the error-notPremium and then attempt fallback
    result = gofile.get_content_from_web(content_id)
    
    if result:
        print(f"\n✓ Fallback returned data: {result.get('status')}")
    else:
        print("\n✗ Fallback failed (expected for dummy ID)")
    
    print("\n" + "=" * 60)
    print("NOTE: To fully test, use a real GoFile content ID")
    print("Example: python3 test_fix.py <real_content_id>")
    print("=" * 60)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Test with provided content ID
        content_id = sys.argv[1]
        print(f"Testing with content ID: {content_id}\n")
        
        gofile = GoFile()
        gofile.update_token()
        gofile.update_wt()
        
        result = gofile.get_content_from_web(content_id)
        
        if result and result.get('status') == 'ok':
            print(f"\n✓ SUCCESS! Retrieved content data")
            data = result.get('data', {})
            print(f"   Type: {data.get('type')}")
            print(f"   Name: {data.get('name')}")
            children = data.get('children', data.get('contents', {}))
            print(f"   Children: {len(children)} items")
        else:
            print(f"\n✗ Failed: {result}")
    else:
        test_api_with_fallback()
