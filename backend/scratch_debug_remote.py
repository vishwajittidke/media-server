import requests
import time

url = "https://media-server-api.onrender.com/api/v1/sync/debug"
headers = {
    "Cookie": "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3ODczMTc2MzMsInN1YiI6ImYxZmYxNTlkLTI4NGEtNGRhMC04NDI1LTcxZWVlMDZiZWYwZiJ9.0sx5sz-C2vYVACkwcI2OhEsEgdhxmf1Hvwy0T_piX9Y"
}

for i in range(20):
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            print(f"Success! Response: {response.text}")
            break
        elif response.status_code == 404:
            print("Render still deploying... (404)")
        else:
            print(f"Status Code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(10)
