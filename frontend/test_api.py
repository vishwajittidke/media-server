import requests
url = "https://media-server-api.onrender.com/api/v1/files/?skip=0&limit=50&target_id=280c0fc0-4747-4596-8612-e4118a370f2a"
try:
    r = requests.get(url)
    print(r.status_code)
    print(r.headers)
    print(r.text[:200])
except Exception as e:
    print(e)
