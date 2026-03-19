#!/usr/bin/env python3
import requests
import json

# Get token
print('Getting token...')
response = requests.post('https://api.gofile.io/accounts', timeout=10)
data = response.json()
print(f'Token response: {json.dumps(data, indent=2)}')

if data.get('status') == 'ok':
    token = data['data']['token']
    print(f'\nToken: {token}')
    
    # Get wt
    print('\nGetting wt...')
    alljs = requests.get('https://gofile.io/dist/js/config.js', timeout=10).text
    if 'appdata.wt = "' in alljs:
        wt = alljs.split('appdata.wt = "')[1].split('"')[0]
        print(f'WT: {wt}')
        
        # Try with different header combinations
        test_id = 'test123'
        
        print('\n--- Test 1: Current headers ---')
        response = requests.get(
            f'https://api.gofile.io/contents/{test_id}',
            headers={
                'Authorization': 'Bearer ' + token,
                'X-Website-Token': wt
            },
            timeout=10
        )
        print(f'Response: {json.dumps(response.json(), indent=2)}')
        
        print('\n--- Test 2: With User-Agent ---')
        response = requests.get(
            f'https://api.gofile.io/contents/{test_id}',
            headers={
                'Authorization': 'Bearer ' + token,
                'X-Website-Token': wt,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            timeout=10
        )
        print(f'Response: {json.dumps(response.json(), indent=2)}')
        
        print('\n--- Test 3: With Origin and Referer ---')
        response = requests.get(
            f'https://api.gofile.io/contents/{test_id}',
            headers={
                'Authorization': 'Bearer ' + token,
                'X-Website-Token': wt,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Origin': 'https://gofile.io',
                'Referer': 'https://gofile.io/'
            },
            timeout=10
        )
        print(f'Response: {json.dumps(response.json(), indent=2)}')
        
        print('\n--- Test 4: Check account tier ---')
        response = requests.get(
            'https://api.gofile.io/accounts/getAccountDetails',
            headers={
                'Authorization': 'Bearer ' + token
            },
            timeout=10
        )
        print(f'Account details: {json.dumps(response.json(), indent=2)}')
