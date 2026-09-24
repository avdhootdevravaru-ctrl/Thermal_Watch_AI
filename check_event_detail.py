import json
import urllib.request

# Check event detail for a high-severity event (id=1925)
try:
    with urllib.request.urlopen("http://localhost:8001/thermal-events/1925", timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print("=== Event 1925 Detail ===")
        print(f"Status: {data.get('status')}")
        print(f"Observation count: {data.get('observation_count')}")
        print(f"Persistence score: {data.get('persistence_score')}")
        print(f"Risk: {data.get('risk')}")
except Exception as e:
    print(f"Error: {e}")

# Also check event 5618 (should be low severity)
print()
try:
    with urllib.request.urlopen("http://localhost:8001/thermal-events/5618", timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print("=== Event 5618 Detail ===")
        print(f"Status: {data.get('status')}")
        print(f"Observation count: {data.get('observation_count')}")
        print(f"Persistence score: {data.get('persistence_score')}")
        print(f"Risk: {data.get('risk')}")
except Exception as e:
    print(f"Error: {e}")

# Check event 2650 (another high severity)
print()
try:
    with urllib.request.urlopen("http://localhost:8001/thermal-events/2650", timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print("=== Event 2650 Detail ===")
        print(f"Status: {data.get('status')}")
        print(f"Observation count: {data.get('observation_count')}")
        print(f"Persistence score: {data.get('persistence_score')}")
        print(f"Risk: {data.get('risk')}")
except Exception as e:
    print(f"Error: {e}")