import requests

url = "https://media-server-api.onrender.com/api/v1/sync/"
headers = {
    "Cookie": "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3ODczMTc2MzMsInN1YiI6ImYxZmYxNTlkLTI4NGEtNGRhMC04NDI1LTcxZWVlMDZiZWYwZiJ9.0sx5sz-C2vYVACkwcI2OhEsEgdhxmf1Hvwy0T_piX9Y",
    "Content-Type": "application/json"
}
payload = {"skip": 0, "limit": 50}

try:
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
