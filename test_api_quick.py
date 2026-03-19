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
        
        # Try to access a test content (using a dummy ID to see the error)
        print('\nTesting API with dummy content ID...')
        test_id = 'test123'
        response = requests.get(
            f'https://api.gofile.io/contents/{test_id}',
            headers={
                'Authorization': 'Bearer ' + token,
                'X-Website-Token': wt
            },
            timeout=10
        )
        print(f'API response: {json.dumps(response.json(), indent=2)}')
