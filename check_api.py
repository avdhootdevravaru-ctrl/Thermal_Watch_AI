import json
import urllib.request

try:
    with urllib.request.urlopen("http://localhost:8001/map/hotspots", timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print("Risk summary:", data.get("risk_summary"))
        print("Total markers:", data.get("total"))
        markers = data.get("markers", [])
        print("First 10 markers:")
        for m in markers[:10]:
            print(f"  id={m['event_id']} sev={m['risk_severity']} score={m['risk_score']}")
except Exception as e:
    print(f"Error: {e}")