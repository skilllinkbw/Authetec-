import base64, json, urllib.request

url = "https://api.github.com/repos/NIT1217/Government-Schemes-Fraud-Duplicate-user-Detection-/readme"
req = urllib.request.Request(url, headers={"User-Agent": "authetec-bench"})
resp = urllib.request.urlopen(req, timeout=15)
data = json.loads(resp.read())
content = base64.b64decode(data["content"]).decode("utf-8")
print(content[:3000])
