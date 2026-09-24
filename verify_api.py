import json
import urllib.request

# Check the /thermal-events endpoint to get full risk distribution
try:
    with urllib.request.urlopen("http://localhost:8001/thermal-events?page_size=10", timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print("=== /thermal-events ===")
        print("Total:", data.get("total"))
        items = data.get("items", [])
        for item in items:
            print(f"  id={item['id']} obs={item['observation_count']} persistence={item['persistence_score']} status={item['status']}")
except Exception as e:
    print(f"Error: {e}")

# Check /map/hotspots with full data
try:
    with urllib.request.urlopen("http://localhost:8001/map/hotspots?limit=500", timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print("\n=== /map/hotspots (limit=500) ===")
        print("Risk summary:", data.get("risk_summary"))
        print("Total markers:", data.get("total"))
        markers = data.get("markers", [])
        # Count severity
        from collections import Counter
        sevs = Counter(m['risk_severity'] for m in markers)
        print("Severity distribution (markers):", dict(sevs))
        # Show a few with non-medium severity
        print("\nNon-medium markers:")
        for m in markers:
            if m['risk_severity'] != 'medium':
                print(f"  id={m['event_id']} sev={m['risk_severity']} score={m['risk_score']}")
except Exception as e:
    print(f"Error: {e}")