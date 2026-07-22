import requests

url = "https://media-server-api.onrender.com/api/v1/files/thumb/4ef36aae42a63927c07364794c1f2721a1c4ca3ab691fa5d009b46e040ebd201.jpeg"
headers = {
    "Cookie": "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3ODczMTc2MzMsInN1YiI6ImYxZmYxNTlkLTI4NGEtNGRhMC04NDI1LTcxZWVlMDZiZWYwZiJ9.0sx5sz-C2vYVACkwcI2OhEsEgdhxmf1Hvwy0T_piX9Y"
}

try:
    response = requests.get(url, headers=headers, timeout=15)
    print(f"Status Code: {response.status_code}")
    print(f"Body: {response.text}")
except Exception as e:
    print(f"Error: {e}")
