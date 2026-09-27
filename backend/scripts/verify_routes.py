import urllib.request
import json
import sys

def check(name, url, is_json=True):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode('utf-8')
            if is_json:
                data = json.loads(body)
                print(f"[PASS] {name:42} -> HTTP {r.status} (Valid JSON)")
                return True, data
            else:
                assert 'root' in body
                print(f"[PASS] {name:42} -> HTTP {r.status} (SPA HTML entrypoint)")
                return True, body
    except Exception as e:
        print(f"[FAIL] {name:42} -> Error: {e}")
        return False, None

print("=== VERIFYING API ROUTES USED BY DASHBOARD ===")
api_checks = [
    ("GET /health", "http://127.0.0.1:8000/health"),
    ("GET /health/model", "http://127.0.0.1:8000/health/model"),
    ("GET /health/database", "http://127.0.0.1:8000/health/database"),
    ("GET /firms/status", "http://127.0.0.1:8000/firms/status"),
    ("GET /ingestion/status", "http://127.0.0.1:8000/ingestion/status"),
    ("GET /map/hotspots", "http://127.0.0.1:8000/map/hotspots?limit=500"),
    ("GET /thermal-events", "http://127.0.0.1:8000/thermal-events?page=1&page_size=20"),
    ("GET /history/statistics", "http://127.0.0.1:8000/history/statistics"),
    ("GET /history/data-quality", "http://127.0.0.1:8000/history/data-quality"),
    ("GET /blockchain/status", "http://127.0.0.1:8000/blockchain/status"),
]

success = True
for name, url in api_checks:
    ok, _ = check(name, url)
    if not ok: success = False

_, ev = check("Events Sample", "http://127.0.0.1:8000/thermal-events?page=1&page_size=1")
if not ev or not ev.get("items"):
    print("[FAIL] No event available for detail-route verification")
    sys.exit(1)
sample_id = ev["items"][0]["id"]

event_checks = [
    (f"GET /thermal-events/{sample_id}", f"http://127.0.0.1:8000/thermal-events/{sample_id}"),
    (f"GET /thermal-events/{sample_id}/risk", f"http://127.0.0.1:8000/thermal-events/{sample_id}/risk"),
    (f"GET /thermal-events/{sample_id}/classification", f"http://127.0.0.1:8000/thermal-events/{sample_id}/classification"),
    (f"GET /thermal-events/{sample_id}/history", f"http://127.0.0.1:8000/thermal-events/{sample_id}/history"),
    (f"GET /thermal-events/{sample_id}/thermal-dna", f"http://127.0.0.1:8000/thermal-events/{sample_id}/thermal-dna"),
    (f"GET /thermal-events/{sample_id}/evidence", f"http://127.0.0.1:8000/thermal-events/{sample_id}/evidence"),
    (f"GET /thermal-events/{sample_id}/weak-classification", f"http://127.0.0.1:8000/thermal-events/{sample_id}/weak-classification"),
    (f"GET /evidence/{sample_id}", f"http://127.0.0.1:8000/evidence/{sample_id}"),
    (f"GET /map/facilities/nearby", f"http://127.0.0.1:8000/map/facilities/nearby?event_id={sample_id}&radius_km=5"),
    (f"GET /history/event/{sample_id}/profile", f"http://127.0.0.1:8000/history/event/{sample_id}/profile"),
]

for name, url in event_checks:
    ok, _ = check(name, url)
    if not ok: success = False

print("\n=== VERIFYING ALL FRONTEND ROUTES ===")
frontend_checks = [
    ("Route / (Dashboard)", "http://localhost:3000/"),
    ("Route /events (Events List)", "http://localhost:3000/events"),
    (f"Route /events/{sample_id} (Event Detail)", f"http://localhost:3000/events/{sample_id}"),
    ("Route /analytics (Intelligence)", "http://localhost:3000/analytics"),
    ("Route /risk (Risk Page)", "http://localhost:3000/risk"),
    ("Route /model (ML Transparency)", "http://localhost:3000/model"),
    ("Route /evidence (Evidence Ledger)", "http://localhost:3000/evidence"),
    ("Route /health (System Status)", "http://localhost:3000/health"),
]

for name, url in frontend_checks:
    ok, _ = check(name, url, is_json=False)
    if not ok: success = False

if success:
    print("\n>>> ALL 20 API ROUTES AND 8 FRONTEND ROUTES VERIFIED: 100% SUCCESS <<<")
    sys.exit(0)
else:
    print("\n>>> FAILURES DETECTED <<<")
    sys.exit(1)
