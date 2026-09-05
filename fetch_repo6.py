import sys, base64, json, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
url = 'https://raw.githubusercontent.com/NIT1217/Government-Schemes-Fraud-Duplicate-user-Detection-/main/README.md'
req = urllib.request.Request(url, headers={'User-Agent': 'authetec'})
content = urllib.request.urlopen(req, timeout=15).read().decode('utf-8')
print(content[:3000])
