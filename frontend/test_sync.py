import requests
url = "https://media-server-api.onrender.com/api/v1/sync/"
try:
    r = requests.post(url)
    print("Status:", r.status_code)
except Exception as e:
    print(e)
