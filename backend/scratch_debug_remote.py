import requests

url = "https://media-server-api.onrender.com/api/v1/sync/debug"
headers = {
    "Cookie": "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3ODczMTc2MzMsInN1YiI6ImYxZmYxNTlkLTI4NGEtNGRhMC04NDI1LTcxZWVlMDZiZWYwZiJ9.0sx5sz-C2vYVACkwcI2OhEsEgdhxmf1Hvwy0T_piX9Y"
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    print(response.json())
except Exception as e:
    print(f"Error: {e}")
