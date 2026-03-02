#!/usr/bin/env python3
import os
import requests
import json

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    print("ERROR: OPENROUTER_API_KEY environment variable not set.")
    print("Get your key from: https://openrouter.ai/keys")
    exit(1)
model = 'deepseek/deepseek-r1-0528:free'

headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://totalreclaw.ai',
}

data = {
    'model': model,
    'messages': [{'role': 'user', 'content': 'Say hello'}],
    'max_tokens': 50,
}

print('Testing OpenRouter API...')
print(f'Model: {model}')

response = requests.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=data, timeout=60)
print(f'Status code: {response.status_code}')
print(f'Response headers: {dict(response.headers)}')
print()

result = response.json()
print('Full response:')
print(json.dumps(result, indent=2))

if 'choices' in result:
    print(f"\nContent: {result['choices'][0]['message']['content']}")
else:
    print("\nNo 'choices' key in response!")
    if 'error' in result:
        print(f"Error: {result['error']}")
