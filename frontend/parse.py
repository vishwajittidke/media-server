import json
with open('deployment.json', 'r', encoding='utf-16') as f:
    data = json.load(f)
print(data.get('meta', {}))
