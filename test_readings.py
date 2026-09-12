import json, urllib.request
resp = json.loads(urllib.request.urlopen('http://127.0.0.1:5000/api/latest').read())
hist = resp.get('readings_history', [])
print(f'readings_history: {len(hist)} readings')
for r in hist[-5:]:
    print(f\"  Temp={r.get('temperature')} Volt={r.get('voltage')} Pred={r.get('prediction')}\")
