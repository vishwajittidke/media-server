import requests
url = "https://frontend-azure-gamma-16.vercel.app/api/v1/files/"
try:
    r = requests.get(url)
    print("GET Status:", r.status_code)
    print("GET Content-Type:", r.headers.get('content-type'))
    r = requests.options(url)
    print("OPTIONS Status:", r.status_code)
    print("OPTIONS Content-Type:", r.headers.get('content-type'))
except Exception as e:
    print(e)
